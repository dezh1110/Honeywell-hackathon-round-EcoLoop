"""
The RC (resistor-capacitor) thermal-model primitives shared by:
  - `app/energyplus/mock_runtime.py` -- the running dev/demo simulation loop
  - `app/agent/whatif.py` -- the What-If Simulator's instant impact estimate

Pulled out on its own so both call the exact same physics instead of two
copies drifting apart. See `mock_runtime.py`'s module docstring for why this
approximation exists and its limits.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

OUTDOOR_MEAN_C = 29.0  # Bengaluru-ish daytime mean, purely for the demo curve
OUTDOOR_SWING_C = 6.0
THERMAL_RC_TAU_MIN = 45.0  # zone time constant: how fast indoor temp chases outdoor+setpoint
INTERNAL_GAIN_C = 1.2  # occupancy/equipment heat gain, applied during "occupied" hours
COOLING_COP = 3.2  # chiller coefficient of performance, for kW-from-setpoint-gap estimate
FLOOR_AREA_PER_ZONE_KW_PER_C = 0.9  # crude per-zone plant capacity scaling


@dataclass
class ZoneState:
    name: str
    air_temp_c: float = 24.0
    cooling_setpoint_c: float = 23.0
    heating_setpoint_c: float = 21.0


def outdoor_temp(sim_clock: datetime) -> float:
    hour = sim_clock.hour + sim_clock.minute / 60.0
    return OUTDOOR_MEAN_C + OUTDOOR_SWING_C * math.sin((hour - 9) / 24 * 2 * math.pi)


def is_occupied(sim_clock: datetime) -> bool:
    return 9 <= sim_clock.hour < 19


def step_zone(zone: ZoneState, sim_clock: datetime, dt_minutes: float) -> float:
    """Advance one zone by dt_minutes of simulated time. Returns instantaneous
    cooling electrical power (kW) drawn to hold/approach setpoint."""
    outdoor = outdoor_temp(sim_clock)
    occupied_gain = INTERNAL_GAIN_C if is_occupied(sim_clock) else 0.0
    target = zone.cooling_setpoint_c
    # First-order response toward (outdoor + internal gains), damped toward setpoint
    # by an idealized proportional controller representing the AHU/thermostat.
    free_drift_target = outdoor * 0.35 + zone.air_temp_c * 0.65 + occupied_gain
    controlled_target = 0.5 * free_drift_target + 0.5 * target
    alpha = 1 - math.exp(-dt_minutes / THERMAL_RC_TAU_MIN)
    new_temp = zone.air_temp_c + (controlled_target - zone.air_temp_c) * alpha

    cooling_gap_c = max(0.0, zone.air_temp_c - target)
    cooling_kw = (cooling_gap_c * FLOOR_AREA_PER_ZONE_KW_PER_C) / COOLING_COP
    zone.air_temp_c = round(new_temp, 3)
    return cooling_kw


def approx_pmv(air_temp_c: float) -> float:
    """Rough Fanger PMV approximation around a 23degC/50%RH comfort neutral
    point, purely for demo purposes (real PMV needs radiant temp, humidity,
    clo, met -- all of which the real EnergyPlus Fanger model outputs directly)."""
    return round((air_temp_c - 23.0) * 0.45, 2)


CO2_AMBIENT_PPM = 420.0  # outdoor/baseline CO2 concentration
CO2_OCCUPIED_RISE_PPM = 380.0  # added ppm from occupant respiration at typical ventilation rates


def estimate_co2_ppm(hour: int) -> float:
    """Rough indoor CO2 concentration estimate (ppm) used as the indoor-air-
    quality signal the spec calls for. A real IAQ reading needs EnergyPlus's
    ZoneAirContaminantBalance (CO2 generation objects, outdoor air ppm,
    ventilation rates) enabled in the IDF -- not done here, since it's a
    second full subsystem to get right. This is a simple occupancy-driven
    estimate, used identically by both the mock and real-EnergyPlus backends
    so the agent always has *some* IAQ signal to reason about, clearly
    labeled as an estimate rather than a measured value."""
    if 9 <= hour < 19:
        occupancy_factor = 0.6 + 0.4 * math.sin(((hour - 9) / 10) * math.pi)
        return round(CO2_AMBIENT_PPM + CO2_OCCUPIED_RISE_PPM * occupancy_factor, 1)
    return CO2_AMBIENT_PPM
