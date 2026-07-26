"""
Turns raw signals the control loop already has into short, proactive
operator-facing recommendations -- the equivalent of "High Risk Alert /
Capacity Warning / Optimization Opportunity" cards. These are logged as
`BuildingLog(event_type="recommendation")` rows, kept distinct from routine
per-cycle decision summaries so the dashboard can render them as a separate
alerts panel instead of mixing them into the scrolling terminal feed.

Deliberately simple, explainable heuristics rather than a second model --
a recommendation you can't audit in one sentence isn't more trustworthy for
being ML-generated.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import settings
from app.telemetry.models import Telemetry

CARBON_PEAK_WARNING_THRESHOLD = 400.0  # gCO2/kWh
CARBON_PEAK_WARNING_HOURS = range(15, 19)  # 15:00-18:59, matches the demo diurnal curve's evening ramp
OVERRIDE_FREQUENCY_WARNING_COUNT = 3
IAQ_WARNING_PPM = 1000.0  # indoor CO2 concentration above which ventilation, not temperature, is the fix


@dataclass
class RecommendationEngine:
    """Tracks a little session-local state (per zone override counts, last
    warning issued) so recommendations don't repeat every single cycle."""

    _override_counts: dict[str, int] = field(default_factory=dict)
    _carbon_warning_active: bool = False
    _override_warning_issued: set[str] = field(default_factory=set)
    _peak_demand_warning_active: bool = False
    _iaq_warning_active: bool = False

    def note_action_source(self, zone: str, source: str) -> None:
        if source in ("safety_clamp", "manual_override"):
            self._override_counts[zone] = self._override_counts.get(zone, 0) + 1

    def check(self, telemetry: Telemetry, sim_hour: int) -> list[str]:
        """Returns zero or more new recommendation messages for this cycle."""
        messages: list[str] = []

        is_peak_window = sim_hour in CARBON_PEAK_WARNING_HOURS
        is_high_carbon = telemetry.grid_carbon_intensity >= CARBON_PEAK_WARNING_THRESHOLD
        if is_peak_window and is_high_carbon and not self._carbon_warning_active:
            messages.append(
                f"Grid carbon intensity is {telemetry.grid_carbon_intensity:.0f} gCO2/kWh and rising into "
                f"the evening peak. Consider pre-cooling zones now to shift load ahead of the peak window."
            )
            self._carbon_warning_active = True
        elif not (is_peak_window and is_high_carbon):
            self._carbon_warning_active = False

        over_peak_demand = telemetry.optimized_kw >= settings.peak_demand_threshold_kw
        if over_peak_demand and not self._peak_demand_warning_active:
            messages.append(
                f"Facility load is {telemetry.optimized_kw:.1f} kW, at or above the "
                f"{settings.peak_demand_threshold_kw:.1f} kW peak demand threshold. Consider relaxing "
                f"non-critical zone setpoints to bring load back under the threshold."
            )
            self._peak_demand_warning_active = True
        elif not over_peak_demand:
            self._peak_demand_warning_active = False

        high_iaq = telemetry.indoor_air_quality_ppm >= IAQ_WARNING_PPM
        if high_iaq and not self._iaq_warning_active:
            messages.append(
                f"Estimated indoor CO2 is {telemetry.indoor_air_quality_ppm:.0f} ppm, above the "
                f"{IAQ_WARNING_PPM:.0f} ppm comfort/health guideline. This needs more outdoor air "
                f"ventilation, not just a temperature setpoint change."
            )
            self._iaq_warning_active = True
        elif not high_iaq:
            self._iaq_warning_active = False

        for zone, count in self._override_counts.items():
            if count >= OVERRIDE_FREQUENCY_WARNING_COUNT and zone not in self._override_warning_issued:
                messages.append(
                    f"{zone} has been overridden or safety-clamped {count} times this session. "
                    f"The scheduled comfort band for this zone may need recalibrating."
                )
                self._override_warning_issued.add(zone)

        avg_temp = telemetry.avg_zone_temp
        if avg_temp < 19.0 or avg_temp > 26.0:
            messages.append(
                f"Average zone temperature is {avg_temp:.1f}C, outside the normal comfort band. "
                f"Check for a stuck actuator or sensor fault before trusting further agent decisions."
            )

        return messages


recommendation_engine = RecommendationEngine()
