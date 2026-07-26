"""Typed payloads exchanged between EnergyPlus, the agent, MCP tools, and Supabase."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ZoneReading(BaseModel):
    zone: str
    air_temp_c: float
    pmv: Optional[float] = None  # Fanger Predicted Mean Vote, -3..+3
    occupant_count: Optional[float] = None


class Telemetry(BaseModel):
    """One closed-loop snapshot: what EnergyPlus reported this cycle."""

    timestamp: datetime = Field(default_factory=utcnow)
    sim_time: str  # simulation clock, e.g. "07/25 14:30:00"
    baseline_kw: float
    optimized_kw: float
    grid_carbon_intensity: float  # gCO2/kWh
    indoor_air_quality_ppm: float = 420.0  # estimated CO2 concentration, see thermal_model.estimate_co2_ppm
    zones: list[ZoneReading]

    @property
    def avg_zone_temp(self) -> float:
        if not self.zones:
            return 22.0
        return sum(z.air_temp_c for z in self.zones) / len(self.zones)


class ControlAction(BaseModel):
    """One ECM decision, injected back into EnergyPlus via an EMS actuator."""

    timestamp: datetime = Field(default_factory=utcnow)
    zone: str
    cooling_setpoint_c: Optional[float] = None
    heating_setpoint_c: Optional[float] = None
    reason: str
    source: Literal["agent", "manual_override", "safety_clamp"] = "agent"


class BuildingLog(BaseModel):
    """Row shape matching the `building_logs` table the dashboard already reads."""

    created_at: datetime = Field(default_factory=utcnow)
    event_type: Literal["grid_carbon", "cooling", "heating", "occupancy", "system", "error", "recommendation"] = "system"
    message: str
    severity: Literal["info", "warning", "critical"] = "info"
    zone: Optional[str] = None
    metric_value: Optional[float] = None


class EnergyPlusRuntimeError(BaseModel):
    """A parsed line from the .err file — fed to the LLM as diagnostic context."""

    severity: Literal["warning", "severe", "fatal"]
    message: str
    raw_line: str
