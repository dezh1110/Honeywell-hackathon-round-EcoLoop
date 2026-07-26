import json
from dataclasses import dataclass, field
from typing import Any

import app.agent.react_agent as react_agent_module


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


@dataclass
class FakeMessage:
    content: str | None
    tool_calls: list[FakeToolCall] | None = None

    def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in self.tool_calls
            ]
        if exclude_none:
            d = {k: v for k, v in d.items() if v is not None}
        return d


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeResponse:
    choices: list[FakeChoice]


class FakeCompletions:
    def __init__(self, script: list[FakeResponse]) -> None:
        self._script = script
        self._i = 0

    def create(self, **kwargs: Any) -> FakeResponse:
        response = self._script[self._i]
        self._i += 1
        return response


class FakeChat:
    def __init__(self, script: list[FakeResponse]) -> None:
        self.completions = FakeCompletions(script)


class FakeClient:
    def __init__(self, script: list[FakeResponse]) -> None:
        self.chat = FakeChat(script)


def test_readonly_tool_set_excludes_setpoint_control() -> None:
    assert "set_zone_setpoint" not in react_agent_module.READ_ONLY_TOOL_NAMES
    assert "set_zone_setpoint" in react_agent_module.CONTROL_TOOL_NAMES


def test_agent_calls_set_zone_setpoint_and_returns_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.mcp.tools.shared_state.get_latest_telemetry", lambda: None
    )

    script = [
        FakeResponse(choices=[FakeChoice(message=FakeMessage(
            content=None,
            tool_calls=[FakeToolCall(
                id="call_1",
                function=FakeFunction(
                    name="set_zone_setpoint",
                    arguments=json.dumps({
                        "zone": "ZONE A",
                        "cooling_setpoint_c": 24.0,
                        "reason": "Carbon intensity is falling, relaxing setpoint.",
                    }),
                ),
            )],
        ))]),
        FakeResponse(choices=[FakeChoice(message=FakeMessage(
            content="Relaxed Zone A cooling setpoint to 24C due to falling grid carbon intensity.",
            tool_calls=None,
        ))]),
    ]

    monkeypatch.setattr(react_agent_module, "build_client", lambda: FakeClient(script))

    summary, trace = react_agent_module.run_reasoning_cycle(sim_time="07/25 14:00:00", error_summary="No issues.")

    assert "Zone A" in summary
    assert len(trace) == 1
    assert trace[0]["tool"] == "set_zone_setpoint"
    assert trace[0]["arguments"]["zone"] == "ZONE A"

    from app.telemetry import shared_state
    action = shared_state.consume_pending_action()
    assert action is not None
    assert action.zone == "ZONE A"
    assert action.cooling_setpoint_c == 24.0
