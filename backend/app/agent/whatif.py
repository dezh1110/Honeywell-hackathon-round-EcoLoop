"""
What-If Simulator backend: given a zone's current state and a proposed
setpoint, estimate the kW delta and resulting comfort (PMV) *before* the
operator commits to it -- this is a fast closed-form estimate using the same
RC thermal model as `mock_runtime.py` (see `thermal_model.py`), not a full
EnergyPlus re-run. That's a deliberate trade-off: instant feedback for
exploration, at the cost of being an approximation. The dashboard should
label it as a prediction, not a guarantee.

Works identically regardless of whether the live simulation backend is
`mock` or `energyplus` -- it's a standalone forward projection, not a read of
the running simulation's actual state beyond the latest telemetry snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.energyplus.thermal_model import ZoneState, approx_pmv, step_zone
from app.telemetry import shared_state

# How far ahead to project, and at what resolution -- 2 hours at 10-minute
# steps is enough for the new setpoint's effect to largely settle out given
# THERMAL_RC_TAU_MIN (see thermal_model.py).
PROJECTION_STEPS = 12
STEP_MINUTES = 10.0


def _comfort_status(pmv: float) -> str:
    if -0.5 <= pmv <= 0.5:
        return "comfortable"
    if -1.0 <= pmv <= 1.0:
        return "slightly uncomfortable"
    return "uncomfortable"


def predict_impact(
    zone: str,
    proposed_cooling_setpoint_c: float | None,
    proposed_heating_setpoint_c: float | None,
) -> dict:
    """Project `zone` forward `PROJECTION_STEPS` steps under the proposed
    setpoint and compare average kW draw to holding the current setpoint.
    Returns a dict matching the `whatif_requests` result columns."""
    telemetry = shared_state.get_latest_telemetry()
    current_temp = 23.0
    current_cooling = 23.0
    if telemetry is not None:
        for z in telemetry.zones:
            if z.zone == zone:
                current_temp = z.air_temp_c
                break

    now = datetime.now(timezone.utc)

    baseline_state = ZoneState(name=zone, air_temp_c=current_temp, cooling_setpoint_c=current_cooling)
    proposed_state = ZoneState(
        name=zone,
        air_temp_c=current_temp,
        cooling_setpoint_c=proposed_cooling_setpoint_c if proposed_cooling_setpoint_c is not None else current_cooling,
        heating_setpoint_c=proposed_heating_setpoint_c if proposed_heating_setpoint_c is not None else 21.0,
    )

    baseline_kw_total = 0.0
    proposed_kw_total = 0.0
    clock = now
    for _ in range(PROJECTION_STEPS):
        clock = clock  # projection uses the same forward clock for both runs
        baseline_kw_total += step_zone(baseline_state, clock, STEP_MINUTES)
        proposed_kw_total += step_zone(proposed_state, clock, STEP_MINUTES)

    baseline_avg_kw = baseline_kw_total / PROJECTION_STEPS
    proposed_avg_kw = proposed_kw_total / PROJECTION_STEPS
    kw_delta = round(proposed_avg_kw - baseline_avg_kw, 3)

    predicted_pmv = approx_pmv(proposed_state.air_temp_c)
    comfort = _comfort_status(predicted_pmv)

    direction = "less" if kw_delta < 0 else "more" if kw_delta > 0 else "the same"
    explanation = (
        f"Projected over the next {int(PROJECTION_STEPS * STEP_MINUTES)} minutes, {zone} would "
        f"settle near {proposed_state.air_temp_c:.1f}C ({comfort}, PMV {predicted_pmv:+.2f}) and draw "
        f"{abs(kw_delta):.2f} kW {direction} than holding the current setpoint."
    )

    return {
        "predicted_kw_delta": kw_delta,
        "predicted_pmv": predicted_pmv,
        "comfort_status": comfort,
        "explanation": explanation,
    }
