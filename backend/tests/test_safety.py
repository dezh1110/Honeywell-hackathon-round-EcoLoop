from app.energyplus.safety import clamp_action
from app.telemetry.models import ControlAction


def test_clamp_within_bounds_unchanged() -> None:
    action = ControlAction(zone="ZONE A", cooling_setpoint_c=23.0, reason="test")
    clamped = clamp_action(action)
    assert clamped.cooling_setpoint_c == 23.0
    assert clamped.source == "agent"


def test_clamp_cooling_too_low() -> None:
    action = ControlAction(zone="ZONE A", cooling_setpoint_c=10.0, reason="test")
    clamped = clamp_action(action)
    assert clamped.cooling_setpoint_c == 21.0  # settings.min_cooling_setpoint_c default
    assert clamped.source == "safety_clamp"


def test_clamp_heating_too_high() -> None:
    action = ControlAction(zone="ZONE A", heating_setpoint_c=40.0, reason="test")
    clamped = clamp_action(action)
    assert clamped.heating_setpoint_c == 22.0  # settings.max_heating_setpoint_c default
    assert clamped.source == "safety_clamp"
