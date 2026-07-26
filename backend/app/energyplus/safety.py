"""Hard setpoint bounds enforced regardless of what the LLM proposes.

Kept as a standalone module (rather than a method on one runtime class) so
every simulation backend -- real EnergyPlus EMS, the mock RC model, and any
future one -- clamps through the exact same code path.
"""
from __future__ import annotations

from app.config import settings
from app.telemetry.models import ControlAction


def clamp_action(action: ControlAction) -> ControlAction:
    clamped = action.model_copy()
    changed = False
    reasons: list[str] = []

    if clamped.cooling_setpoint_c is not None:
        bounded = min(
            max(clamped.cooling_setpoint_c, settings.min_cooling_setpoint_c),
            settings.max_cooling_setpoint_c,
        )
        if bounded != clamped.cooling_setpoint_c:
            changed = True
            reasons.append(
                f"cooling setpoint {clamped.cooling_setpoint_c:.1f}C -> clamped to {bounded:.1f}C "
                f"(bounds: {settings.min_cooling_setpoint_c:.1f}-{settings.max_cooling_setpoint_c:.1f}C)"
            )
        clamped.cooling_setpoint_c = bounded

    if clamped.heating_setpoint_c is not None:
        bounded = min(
            max(clamped.heating_setpoint_c, settings.min_heating_setpoint_c),
            settings.max_heating_setpoint_c,
        )
        if bounded != clamped.heating_setpoint_c:
            changed = True
            reasons.append(
                f"heating setpoint {clamped.heating_setpoint_c:.1f}C -> clamped to {bounded:.1f}C "
                f"(bounds: {settings.min_heating_setpoint_c:.1f}-{settings.max_heating_setpoint_c:.1f}C)"
            )
        clamped.heating_setpoint_c = bounded

    if changed:
        clamped.source = "safety_clamp"
        # Self-correction feedback: the LLM sees this on its *next* reasoning
        # cycle (see react_agent.run_reasoning_cycle), so a proposal that got
        # clamped this cycle can actually change the agent's behavior next
        # cycle instead of silently repeating the same out-of-bounds request
        # every time. Imported lazily to avoid a module-level import cycle
        # (shared_state doesn't need to know about safety, only the reverse).
        from app.telemetry import shared_state  # noqa: PLC0415

        shared_state.note_correction(
            f"{clamped.zone}: your last proposal was out of bounds and got corrected -- "
            + "; ".join(reasons)
        )

    return clamped
