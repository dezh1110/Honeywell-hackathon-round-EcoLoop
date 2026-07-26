from app.energyplus.safety import clamp_action
from app.telemetry import shared_state
from app.telemetry.models import ControlAction


def test_clamp_records_correction_note() -> None:
    shared_state._correction_notes.clear()  # isolate from other tests' state
    action = ControlAction(zone="ZONE B", cooling_setpoint_c=10.0, reason="test")
    clamp_action(action)

    notes = shared_state.get_recent_corrections()
    assert len(notes) == 1
    assert "ZONE B" in notes[0]
    assert "clamped" in notes[0]


def test_clamp_without_violation_records_no_note() -> None:
    shared_state._correction_notes.clear()
    action = ControlAction(zone="ZONE C", cooling_setpoint_c=23.0, reason="test")
    clamp_action(action)
    assert shared_state.get_recent_corrections() == []


def test_correction_notes_capped_at_max_length() -> None:
    shared_state._correction_notes.clear()
    for i in range(10):
        shared_state.note_correction(f"note {i}")
    notes = shared_state.get_recent_corrections()
    assert len(notes) == shared_state._MAX_CORRECTION_NOTES
    assert notes[-1] == "note 9"
