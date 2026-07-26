"""
Runs the same IDF/EPW as the agent-controlled simulation, but with the
thermostat schedules left completely untouched -- no actuator overrides,
ever -- to give the dashboard a genuine baseline-vs-optimized comparison for
the real EnergyPlus backend too (the mock RC-model backend already had this,
see mock_runtime.py).

Design note -- why this runs sequentially before the optimized run, not
concurrently with it:
    The first version of this module ran the baseline in a background
    thread alongside the agent-controlled run in the main thread, both
    calling into EnergyPlus's C++ core simultaneously. Testing that against
    a real EnergyPlus install surfaced a real bug: the baseline thread's
    reported power appeared to freeze at a single early value for the rest
    of the run. Two threads both making blocking native (ctypes) calls into
    EnergyPlus, each needing to reacquire the GIL on every Python callback
    invocation, is not a reliable way to get genuine wall-clock concurrency
    here, and a frozen "baseline" number would be a worse failure than no
    live baseline at all -- it looks correct while being wrong.

    Instead, the baseline is simulated once, fully, before the optimized run
    starts, and its per-timestep facility power is cached by simulation
    timestamp. The optimized run then looks up the matching baseline value
    for the same point in simulated time. This is also how real building
    baseline comparisons are normally done in practice (e.g. ASHRAE
    Guideline 14-style calibrated baseline modeling): compute the baseline
    once, compare live operation against it -- not two clocks racing each
    other.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger("ecoloop.baseline")


class BaselineRunner:
    """Runs the unmodified building model to completion (blocking) and
    caches its per-timestep facility power, keyed by the same `sim_time`
    string format `EnergyPlusRuntime` uses (e.g. "07/03 14:30:00"), so the
    optimized run can look up the matching baseline value for any timestep."""

    def __init__(self) -> None:
        try:
            from pyenergyplus.api import EnergyPlusAPI  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - only hit without EnergyPlus installed
            raise RuntimeError(
                "pyenergyplus not importable for the baseline runner. Same requirement as "
                "EnergyPlusRuntime -- see README."
            ) from exc

        self._api = EnergyPlusAPI()
        self._state = self._api.state_manager.new_state()
        self._kw_by_sim_time: dict[str, float] = {}
        self._meter_handle: Optional[int] = None
        self._handles_ready = False
        self._last_kw = 0.0

        self._api.runtime.callback_end_zone_timestep_after_zone_reporting(
            self._state, self._on_timestep
        )

    def _on_timestep(self, ep_state) -> None:  # noqa: ANN001
        ex = self._api.exchange
        if ex.warmup_flag(self._state):
            return
        if not self._handles_ready:
            # Same meter-name substitution as EnergyPlusRuntime, and for the
            # same reason: this EnergyPlus build's Data Exchange API returns
            # an invalid handle for "Electricity:Facility" specifically.
            self._meter_handle = ex.get_meter_handle(self._state, "Electricity:Building")
            self._handles_ready = True

        facility_j = ex.get_meter_value(self._state, self._meter_handle)
        timestep_hours = ex.zone_time_step(self._state)
        kw = (facility_j / 3_600_000.0) / timestep_hours if timestep_hours > 0 else 0.0

        sim_time = (
            f"{ex.month(self._state):02d}/{ex.day_of_month(self._state):02d} "
            f"{ex.hour(self._state):02d}:{int(ex.minutes(self._state)):02d}:00"
        )
        self._kw_by_sim_time[sim_time] = kw
        self._last_kw = kw

    def run(self) -> int:
        """Blocking call: runs the full baseline simulation. Call this
        BEFORE starting the optimized run, not concurrently with it."""
        output_dir = str(Path(settings.output_dir) / "baseline")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        args = ["-w", settings.epw_path, "-d", output_dir, "-r", settings.idf_path]
        logger.info("Running baseline (unactuated) EnergyPlus simulation: %s", " ".join(args))
        exit_code = self._api.runtime.run_energyplus(self._state, args)
        logger.info(
            "Baseline run finished with exit code %s, %d timesteps cached",
            exit_code, len(self._kw_by_sim_time),
        )
        return exit_code

    def kw_at(self, sim_time: str) -> float:
        """Returns the baseline facility power (kW) at the given sim_time,
        or the most recent known value if that exact timestamp wasn't
        captured (e.g. differing sub-hourly rounding) -- better than
        silently returning 0 or crashing the live control loop over a
        lookup miss."""
        if sim_time in self._kw_by_sim_time:
            return self._kw_by_sim_time[sim_time]
        return self._last_kw
