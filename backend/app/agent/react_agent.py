"""
ReAct-style agent loop: the LLM alternates between reasoning and calling MCP
tools (invoked here as direct in-process function calls -- see
`app/mcp/tools.py` and `app/telemetry/shared_state.py` for why that's the
same contract as talking to the MCP server over stdio/SSE) until it either
proposes a setpoint change (or answers a question) or concludes it's done.

Two entry points share one engine (`_run_agent_loop`):
  - `run_reasoning_cycle` -- the control loop, full tool set including
    `set_zone_setpoint`, called every decision cycle from the simulation.
  - `answer_nlp_question` -- the dashboard's "NLP Insights" panel, read-only
    tool set (no `set_zone_setpoint`), called on demand for operator questions.

Both return `(answer, trace)` where `trace` is the ordered list of tool calls
the model made and what they returned -- this is what lets the dashboard show
*why* the agent did something, not just the one-line summary.
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from app.agent.llm_client import build_client
from app.agent.prompts import (
    NLP_QA_SYSTEM_PROMPT,
    NLP_QA_USER_TEMPLATE,
    SYSTEM_PROMPT,
    USER_TURN_TEMPLATE,
)
from app.config import settings
from app.mcp import tools
from app.telemetry import shared_state

logger = logging.getLogger("ecoloop.agent")

TOOL_SCHEMAS = {
    "get_current_telemetry": {
        "type": "function",
        "function": {
            "name": "get_current_telemetry",
            "description": tools.get_current_telemetry.__doc__,
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "get_grid_carbon": {
        "type": "function",
        "function": {
            "name": "get_grid_carbon",
            "description": tools.get_grid_carbon.__doc__,
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "get_recent_errors": {
        "type": "function",
        "function": {
            "name": "get_recent_errors",
            "description": tools.get_recent_errors.__doc__,
            "parameters": {
                "type": "object",
                "properties": {"max_items": {"type": "integer", "default": 10}},
            },
        },
    },
    "list_zones": {
        "type": "function",
        "function": {
            "name": "list_zones",
            "description": tools.list_zones.__doc__,
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "set_zone_setpoint": {
        "type": "function",
        "function": {
            "name": "set_zone_setpoint",
            "description": tools.set_zone_setpoint.__doc__,
            "parameters": {
                "type": "object",
                "properties": {
                    "zone": {"type": "string"},
                    "cooling_setpoint_c": {"type": "number"},
                    "heating_setpoint_c": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["zone", "reason"],
            },
        },
    },
}

_TOOL_IMPL: dict[str, Callable[..., object]] = {
    "get_current_telemetry": tools.get_current_telemetry,
    "get_grid_carbon": tools.get_grid_carbon,
    "get_recent_errors": tools.get_recent_errors,
    "list_zones": tools.list_zones,
    "set_zone_setpoint": tools.set_zone_setpoint,
}

CONTROL_TOOL_NAMES = list(TOOL_SCHEMAS.keys())
READ_ONLY_TOOL_NAMES = [n for n in TOOL_SCHEMAS if n != "set_zone_setpoint"]


def _dispatch_tool_call(name: str, arguments_json: str) -> object:
    fn = _TOOL_IMPL.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        args = json.loads(arguments_json) if arguments_json else {}
        return fn(**args)
    except Exception as exc:  # noqa: BLE001 - a bad tool call must not crash the caller
        logger.exception("Tool call %s failed", name)
        return {"error": str(exc)}


def _run_agent_loop(
    system_prompt: str, user_prompt: str, allowed_tools: list[str]
) -> tuple[str, list[dict]]:
    """Shared ReAct engine. Returns (final_answer, trace) where trace is
    [{"tool": name, "arguments": {...}, "result": {...}}, ...] in call order."""
    client = build_client()
    schemas = [TOOL_SCHEMAS[name] for name in allowed_tools]
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    trace: list[dict] = []

    for _ in range(settings.llm_max_tool_iterations):
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=schemas,
            temperature=settings.llm_temperature,
        )
        choice = response.choices[0]
        messages.append(choice.message.model_dump(exclude_none=True))

        if not choice.message.tool_calls:
            return choice.message.content or "(no answer returned)", trace

        for call in choice.message.tool_calls:
            args = json.loads(call.function.arguments) if call.function.arguments else {}
            result = _dispatch_tool_call(call.function.name, call.function.arguments)
            trace.append({"tool": call.function.name, "arguments": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )

    return "Reached max tool-call iterations without a final answer.", trace


def run_reasoning_cycle(sim_time: str, error_summary: str) -> tuple[str, list[dict]]:
    """One full control-loop ReAct cycle. Returns (summary, trace). Any
    setpoint change is picked up separately via `shared_state.consume_pending_action`."""
    user_prompt = (
        USER_TURN_TEMPLATE.format(sim_time=sim_time)
        + f"\n\nMost recent EnergyPlus runtime diagnostics:\n{error_summary}"
    )
    corrections = shared_state.get_recent_corrections()
    if corrections:
        # Self-correction loop: the agent sees what it got wrong last time
        # (a proposal that was out of safety bounds) so it can actually
        # adjust future proposals, not just have them silently clamped every
        # cycle with no memory of it happening.
        user_prompt += "\n\nSelf-correction notes from recent cycles (adjust your proposals accordingly):\n" + "\n".join(
            f"- {note}" for note in corrections
        )
    return _run_agent_loop(SYSTEM_PROMPT, user_prompt, CONTROL_TOOL_NAMES)


def answer_nlp_question(question: str) -> tuple[str, list[dict]]:
    """One read-only ReAct pass answering an operator's natural-language
    question. `set_zone_setpoint` is deliberately excluded from the tool set --
    this path can look at the building, never change it."""
    user_prompt = NLP_QA_USER_TEMPLATE.format(question=question)
    return _run_agent_loop(NLP_QA_SYSTEM_PROMPT, user_prompt, READ_ONLY_TOOL_NAMES)
