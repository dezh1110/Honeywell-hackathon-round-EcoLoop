"""
Real-time closed-loop bridge between a running EnergyPlus simulation and the
agent, built on EnergyPlus's official Python EMS API (`pyenergyplus`).

Why the EMS API and not eppy/BCVTB file-rewriting:
    Rewriting the IDF between separate `runenergyplus` invocations is not a
    closed loop, it's a batch loop — the agent only ever sees a finished run.
    The EMS Python API instead registers a callback that fires every zone
    timestep *while EnergyPlus is running*, giving the agent live sensor data
    (zone temps, PMV, facility electricity) and a live actuator (thermostat
    setpoint schedule override) to write back into the same simulation. That
    is the "Feedback -> Reasoning -> Control -> Forward Injection" loop the
    spec calls for.

Requires a local EnergyPlus >= 9.3 installation (sets PYTHONPATH to the
install dir, or set ENERGYPLUS_INSTALL_DIR so this module can locate
`pyenergyplus`). See README for installation notes.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from app.config import settings
from app.energyplus.idf_utils import parse_err_file, summarize_errors
from app.energyplus.safety import clamp_action
from app.energyplus.thermal_model import estimate_co2_ppm
from app.telemetry.models import ControlAction, Telemetry, ZoneReading

if TYPE_CHECKING:
    from app.energyplus.baseline_runner import BaselineRunner

logger = logging.getLogger("ecoloop.energyplus")

DecisionFn = Callable[[Telemetry, str], Optional[ControlAction]]
"""Given the latest telemetry snapshot and a text summary of recent runtime
errors, return the next ControlAction (or None to keep current setpoints)."""


def _ensure_pyenergyplus_importable() -> None:
    install_dir = Path(settings.energyplus_install_dir)
    if str(install_dir) not in sys.path and install_dir.exists():
        sys.path.insert(0, str(install_dir))


class EnergyPlusRuntime:
    """One live simulation session with an injected decision callback."""

    def __init__(self, decision_fn: DecisionFn, baseline: Optional["BaselineRunner"] = None) -> None:
        _ensure_pyenergyplus_importable()
        try:
            from pyenergyplus.api import EnergyPlusAPI  # noqa: PLC0415 (optional heavy import)
        except ImportError as exc:  # pragma: no cover - exercised only without EnergyPlus installed
            raise RuntimeError(
                "pyenergyplus not importable. Install EnergyPlus locally and set "
                "ENERGYPLUS_INSTALL_DIR, e.g. /usr/local/EnergyPlus-24-1-0."
            ) from exc

        self._api = EnergyPlusAPI()
        self._state = self._api.state_manager.new_state()
        self._decision_fn = decision_fn
        self._baseline = baseline
        self._timestep_counter = 0
        self._sensor_handles: dict[str, int] = {}
        self._actuator_handles: dict[str, dict[str, int]] = {}
        self._meter_handle: Optional[int] = None
        self._handles_ready = False
        self._current_action: dict[str, ControlAction] = {}

        self._api.runtime.callback_begin_zone_timestep_after_init_heat_balance(
            self._state, self._on_timestep
        )

    # -- lifecycle -----------------------------------------------------
    def run(self) -> int:
        """Blocking call: runs the full simulation. Returns the EnergyPlus exit code."""
        Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
        args = [
            "-w", settings.epw_path,
            "-d", settings.output_dir,
            "-r",
            settings.idf_path,
        ]
        logger.info("Starting EnergyPlus: %s", " ".join(args))
        exit_code = self._api.runtime.run_energyplus(self._state, args)
        err_path = Path(settings.output_dir) / "eplusout.err"
        errors = parse_err_file(err_path)
        if errors:
            logger.warning("EnergyPlus run finished with issues:\n%s", summarize_errors(errors))
        return exit_code

    def stop(self) -> None:
        self._api.runtime.stop_simulation(self._state)

    # -- EMS handle registration ----------------------------------------
    def _register_handles(self) -> None:
        ex = self._api.exchange
        for zone in settings.zone_names:
            self._sensor_handles[f"temp::{zone}"] = ex.get_variable_handle(
                self._state, "Zone Mean Air Temperature", zone
            )
            # PMV is keyed by the zone's People object name, not the zone
            # name itself -- this project's IDF names it "<ZoneNoSpaces> People"
            # (e.g. "ZoneA People" for "ZONE A").
            people_key = f"{zone.title().replace(' ', '')} People"
            self._sensor_handles[f"pmv::{zone}"] = ex.get_variable_handle(
                self._state, "Zone Thermal Comfort Fanger Model PMV", people_key
            )
            self._actuator_handles[zone] = {
                "cooling": ex.get_actuator_handle(
                    self._state, "Zone Temperature Control", "Cooling Setpoint", zone
                ),
                "heating": ex.get_actuator_handle(
                    self._state, "Zone Temperature Control", "Heating Setpoint", zone
                ),
            }
        # NOTE: "Electricity:Facility" is registered in the model (it shows up
        # in eplusout.mdd) but this EnergyPlus build's Data Exchange API
        # returns handle -1 for it specifically -- confirmed by testing
        # against a real install, not assumed. "Electricity:Building" is
        # exposed by the same API and is numerically identical for this
        # model (no exterior-only end uses), so it's used instead. If you
        # add exterior lighting/equipment to the model, revisit this.
        self._meter_handle = ex.get_meter_handle(self._state, "Electricity:Building")
        self._handles_ready = True

    # -- per-timestep callback -------------------------------------------
    def _on_timestep(self, ep_state) -> None:  # noqa: ANN001 - EnergyPlus passes its own state handle
        ex = self._api.exchange
        if ex.warmup_flag(self._state):
            return
        if not self._handles_ready:
            self._register_handles()

        self._timestep_counter += 1

        zones: list[ZoneReading] = []
        for zone in settings.zone_names:
            air_temp = ex.get_variable_value(self._state, self._sensor_handles[f"temp::{zone}"])
            pmv_handle = self._sensor_handles.get(f"pmv::{zone}", -1)
            pmv = ex.get_variable_value(self._state, pmv_handle) if pmv_handle != -1 else None
            zones.append(ZoneReading(zone=zone, air_temp_c=round(air_temp, 2), pmv=round(pmv, 2) if pmv is not None else None))

        facility_j = ex.get_meter_value(self._state, self._meter_handle)
        # Meter values accumulate over one zone timestep, NOT a fixed hour --
        # `zone_time_step()` returns the current timestep length in fractional
        # hours (e.g. 1/6 for a 10-minute timestep), so this is the correct
        # divisor for average kW over that timestep. Dividing by a fixed
        # 3,600,000 (seconds/hour) here would silently under-report power by
        # (60 / timestep_minutes) -- caught by comparing against eplusout.csv
        # during a real test run, not assumed correct.
        timestep_hours = ex.zone_time_step(self._state)
        facility_kw = (facility_j / 3_600_000.0) / timestep_hours if timestep_hours > 0 else 0.0

        sim_time = (
            f"{ex.month(self._state):02d}/{ex.day_of_month(self._state):02d} "
            f"{ex.hour(self._state):02d}:{int(ex.minutes(self._state)):02d}:00"
        )

        telemetry = Telemetry(
            sim_time=sim_time,
            baseline_kw=self._baseline.kw_at(sim_time) if self._baseline is not None else facility_kw,
            optimized_kw=facility_kw,
            grid_carbon_intensity=0.0,  # filled in by the agent layer (carbon provider)
            indoor_air_quality_ppm=estimate_co2_ppm(ex.hour(self._state)),
            zones=zones,
        )

        if self._timestep_counter % settings.agent_decision_every_n_timesteps != 0:
            return

        err_path = Path(settings.output_dir) / "eplusout.err"
        error_summary = summarize_errors(parse_err_file(err_path))

        action = self._decision_fn(telemetry, error_summary)
        if action is None:
            return

        self._apply_action(action)

    # -- forward injection -------------------------------------------------
    def _apply_action(self, action: ControlAction) -> None:
        ex = self._api.exchange
        handles = self._actuator_handles.get(action.zone)
        if not handles:
            logger.warning("No actuator handles registered for zone %s", action.zone)
            return

        clamped = clamp_action(action)
        if clamped.cooling_setpoint_c is not None:
            ex.set_actuator_value(self._state, handles["cooling"], clamped.cooling_setpoint_c)
        if clamped.heating_setpoint_c is not None:
            ex.set_actuator_value(self._state, handles["heating"], clamped.heating_setpoint_c)
        self._current_action[action.zone] = clamped
