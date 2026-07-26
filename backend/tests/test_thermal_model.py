from datetime import datetime, timezone

from app.energyplus.thermal_model import ZoneState, approx_pmv, estimate_co2_ppm, step_zone


def test_step_zone_moves_toward_setpoint() -> None:
    zone = ZoneState(name="TEST", air_temp_c=28.0, cooling_setpoint_c=23.0)
    clock = datetime(2026, 7, 26, 14, 0, tzinfo=timezone.utc)
    step_zone(zone, clock, dt_minutes=10.0)
    assert zone.air_temp_c < 28.0  # should cool toward setpoint, not stay put or rise


def test_approx_pmv_neutral_at_23c() -> None:
    assert approx_pmv(23.0) == 0.0
    assert approx_pmv(26.0) > 0  # warmer than neutral -> positive PMV (warm sensation)
    assert approx_pmv(20.0) < 0  # cooler than neutral -> negative PMV (cool sensation)


def test_estimate_co2_ppm_higher_when_occupied() -> None:
    occupied = estimate_co2_ppm(hour=13)  # midday, inside the 9-19 occupied window
    unoccupied = estimate_co2_ppm(hour=2)  # overnight
    assert occupied > unoccupied
    assert unoccupied == 420.0
