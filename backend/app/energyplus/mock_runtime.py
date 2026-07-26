"""
A minimal first-order RC (resistor-capacitor) thermal model standing in for
EnergyPlus, so the rest of the stack -- MCP tools, ReAct agent, Supabase
telemetry, the dashboard -- can be built, demoed, and load-tested without a
~1GB native EnergyPlus install on hand. It implements exactly the same
`DecisionFn` contract as `EnergyPlusRuntime` (see runtime.py), so switching
`SIMULATION_BACKEND=energyplus` in `.env` once EnergyPlus is installed
requires no other code changes anywhere in the agent.

It also runs a second, un-actuated instance of the same model side by side
("baseline") purely on a fixed thermostat schedule, so the dashboard's
baseline-vs-optimized comparison reflects an actual counterfactual rather
than a made-up number.

The underlying physics primitives live in `app/energyplus/thermal_model.py`
and are shared with `app/agent/whatif.py` (the What-If Simulator's instant
impact estimate) so both use the exact same model instead of two copies
drifting apart.

This is explicitly NOT a substitute for the real physics engine required by
the spec -- see README "Running against real EnergyPlus".
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.energyplus.runtime import DecisionFn
from app.energyplus.safety import clamp_action
from app.energyplus.thermal_model import ZoneState, approx_pmv, estimate_co2_ppm, step_zone
from app.telemetry.models import ZoneReading

logger = logging.getLogger("ecoloop.mock_runtime")


@dataclass
class _ModelState:
    zones: dict[str, ZoneState] = field(default_factory=dict)
    sim_clock: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MockRuntime:
    """Drives the RC model forward in (accelerated) wall-clock time, calling
    `decision_fn` on the same cadence a real EnergyPlus run would."""

    def __init__(self, decision_fn: DecisionFn, seconds_per_tick: float = 2.0,
                 sim_minutes_per_tick: float = 10.0) -> None:
        self._decision_fn = decision_fn
        self._seconds_per_tick = seconds_per_tick
        self._sim_minutes_per_tick = sim_minutes_per_tick
        self._optimized = _ModelState(
            zones={z: ZoneState(name=z) for z in settings.zone_names}
        )
        self._baseline = _ModelState(
            zones={z: ZoneState(name=z) for z in settings.zone_names}
        )
        self._tick = 0
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> int:
        logger.info(
            "Starting mock RC thermal simulation (%.0fs wall-clock = %.0f sim-minutes per tick)",
            self._seconds_per_tick, self._sim_minutes_per_tick,
        )
        while not self._stop_event.is_set():
            self._tick += 1
            dt = timedelta(minutes=self._sim_minutes_per_tick)
            self._optimized.sim_clock += dt
            self._baseline.sim_clock += dt

            optimized_kw = sum(
                step_zone(z, self._optimized.sim_clock, self._sim_minutes_per_tick)
                for z in self._optimized.zones.values()
            )
            baseline_kw = sum(
                step_zone(z, self._baseline.sim_clock, self._sim_minutes_per_tick)
                for z in self._baseline.zones.values()
            )

            if self._tick % settings.agent_decision_every_n_timesteps == 0:
                from app.energyplus.idf_utils import parse_err_file, summarize_errors  # noqa: PLC0415
                from pathlib import Path  # noqa: PLC0415

                zones = [
                    ZoneReading(
                        zone=z.name,
                        air_temp_c=z.air_temp_c,
                        pmv=approx_pmv(z.air_temp_c),
                    )
                    for z in self._optimized.zones.values()
                ]
                from app.telemetry.models import Telemetry  # noqa: PLC0415

                telemetry = Telemetry(
                    sim_time=self._optimized.sim_clock.strftime("%m/%d %H:%M:%S"),
                    baseline_kw=round(baseline_kw, 2),
                    optimized_kw=round(optimized_kw, 2),
                    grid_carbon_intensity=0.0,
                    indoor_air_quality_ppm=estimate_co2_ppm(self._optimized.sim_clock.hour),
                    zones=zones,
                )
                err_path = Path(settings.output_dir) / "eplusout.err"
                error_summary = summarize_errors(parse_err_file(err_path))

                action = self._decision_fn(telemetry, error_summary)
                if action is not None:
                    action = clamp_action(action)
                    zone = self._optimized.zones.get(action.zone)
                    if zone is not None:
                        if action.cooling_setpoint_c is not None:
                            zone.cooling_setpoint_c = action.cooling_setpoint_c
                        if action.heating_setpoint_c is not None:
                            zone.heating_setpoint_c = action.heating_setpoint_c

            time.sleep(self._seconds_per_tick)
        return 0
