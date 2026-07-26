"""
The actual tool implementations. Kept as plain, undecorated functions so they
can be:
  (a) wrapped with `@mcp.tool()` in `server.py` and served over the MCP
      protocol (stdio or SSE) to any MCP-speaking client, and
  (b) called directly, in-process, by the ReAct agent for the tight
      per-timestep decision loop, with zero transport overhead.

Docstrings double as the tool descriptions an LLM sees over MCP, so they're
written for that audience.
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.energyplus.idf_utils import list_zone_names, parse_err_file, summarize_errors
from app.telemetry import shared_state
from app.telemetry.carbon import get_grid_carbon_intensity


def list_zones() -> list[str]:
    """List every thermal zone in the currently loaded building model."""
    zones = list_zone_names(settings.idf_path)
    return zones or settings.zone_names


def get_current_telemetry() -> dict:
    """Get the latest sensor snapshot: per-zone air temperature, facility
    electricity draw (baseline vs. optimized, kW), estimated indoor air
    quality (CO2 ppm), and the simulation clock time. Also returns
    `peak_demand_threshold_kw` -- compare `optimized_kw` against this to
    judge whether the building is at risk of a peak-demand violation.
    Call this first, every reasoning cycle, before deciding on any action.
    """
    telemetry = shared_state.get_latest_telemetry()
    if telemetry is None:
        return {"error": "No telemetry yet - simulation may still be warming up."}
    payload = telemetry.model_dump(mode="json")
    payload["peak_demand_threshold_kw"] = settings.peak_demand_threshold_kw
    return payload


def get_grid_carbon() -> dict:
    """Get the current grid carbon intensity in gCO2/kWh. Use this to decide
    whether to pre-cool/pre-heat opportunistically (low carbon) or coast on
    thermal mass and relax setpoints (high carbon, e.g. evening peak)."""
    return {"grid_carbon_intensity_gco2_per_kwh": get_grid_carbon_intensity()}


def get_recent_errors(max_items: int = 10) -> str:
    """Parse the EnergyPlus .err log from the current run and return a
    compact digest of warnings/severe/fatal issues. Use this if telemetry
    looks anomalous (e.g. a zone temperature is frozen or physically
    implausible) to check whether the simulation itself is degraded."""
    err_path = Path(settings.output_dir) / "eplusout.err"
    return summarize_errors(parse_err_file(err_path), max_items=max_items)


def set_zone_setpoint(zone: str, cooling_setpoint_c: float | None = None,
                       heating_setpoint_c: float | None = None, reason: str = "") -> dict:
    """Propose a new cooling and/or heating setpoint for a zone. This is the
    only way to actuate the building. Values are clamped server-side to safe
    comfort bounds regardless of what you request, and every call is logged
    with your stated reason for audit. Always pass a concise `reason`
    explaining the ECM logic (e.g. which signal triggered it)."""
    if cooling_setpoint_c is None and heating_setpoint_c is None:
        return {"error": "Provide at least one of cooling_setpoint_c / heating_setpoint_c."}
    action = shared_state.propose_action(
        zone=zone,
        cooling_setpoint_c=cooling_setpoint_c,
        heating_setpoint_c=heating_setpoint_c,
        reason=reason or "No reason provided.",
    )
    return action.model_dump(mode="json")
