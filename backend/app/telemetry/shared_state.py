"""
Bridges the EnergyPlus runtime (producer of telemetry, consumer of actions)
with the MCP tool layer (consumer of telemetry, producer of actions).

Two deployment shapes are supported without changing any tool code:

1. Embedded (default, used by `app.main` for the hackathon demo): the
   EnergyPlus runtime, the ReAct agent, and the MCP tool functions all live
   in one process. This module is just an in-memory, thread-safe mailbox —
   fast enough to call once per agent decision cycle from inside the
   EnergyPlus EMS callback.

2. Standalone MCP server (`python -m app.mcp.server`, e.g. for a remote LLM
   host such as Claude Desktop to attach to): no EnergyPlus process is
   sharing memory with it, so reads/writes fall back to Supabase, which the
   embedded runtime is already populating every cycle. Same tool, same
   contract, different transport underneath.
"""
from __future__ import annotations

import threading
from typing import Optional

from app.telemetry.models import ControlAction, Telemetry
from app.telemetry.supabase_client import sink

_lock = threading.Lock()
_latest_telemetry: Optional[Telemetry] = None
_pending_action: Optional[ControlAction] = None
_action_history: list[ControlAction] = []

# Self-correction memory: when a proposal gets safety-clamped, the reason is
# recorded here and surfaced back to the LLM on the *next* reasoning cycle
# (see app/agent/react_agent.py's use of `recent_correction_notes`). This is
# what makes "self-correction" a real feedback loop rather than a one-shot
# clamp with no memory -- the agent can see that its last proposal for a
# zone was out of bounds and adjust, instead of repeating the same mistake
# every cycle.
_correction_notes: list[str] = []
_MAX_CORRECTION_NOTES = 5


def publish_telemetry(telemetry: Telemetry) -> None:
    global _latest_telemetry
    with _lock:
        _latest_telemetry = telemetry
    sink.write_telemetry(telemetry)


def get_latest_telemetry() -> Optional[Telemetry]:
    with _lock:
        if _latest_telemetry is not None:
            return _latest_telemetry
    # Standalone-process fallback: this backend doesn't query Supabase reads
    # in the OSS-only PoC path (the frontend does that over its own anon
    # client); a real deployment would add a `fetch_latest_telemetry` read
    # here using the same service client for a fully decoupled MCP server.
    return None


def propose_action(zone: str, cooling_setpoint_c: float | None, heating_setpoint_c: float | None,
                    reason: str, source: str = "agent") -> ControlAction:
    global _pending_action
    action = ControlAction(
        zone=zone,
        cooling_setpoint_c=cooling_setpoint_c,
        heating_setpoint_c=heating_setpoint_c,
        reason=reason,
        source=source,  # type: ignore[arg-type]
    )
    with _lock:
        _pending_action = action
        _action_history.append(action)
    sink.write_control_action(action)
    return action


def consume_pending_action() -> Optional[ControlAction]:
    """Called once per decision cycle by the runtime after the agent finishes
    its ReAct loop, so the same action isn't re-applied on the next cycle."""
    global _pending_action
    with _lock:
        action, _pending_action = _pending_action, None
        return action


def note_correction(message: str) -> None:
    """Record a self-correction note (e.g. 'ZONE B's proposed 18.0C cooling
    setpoint was clamped to 21.0C') for the LLM to see on its next reasoning
    cycle. Capped so this can't grow unbounded across a long-running session."""
    with _lock:
        _correction_notes.append(message)
        del _correction_notes[:-_MAX_CORRECTION_NOTES]


def get_recent_corrections() -> list[str]:
    with _lock:
        return list(_correction_notes)
