from app.agent.whatif import predict_impact


def test_predict_impact_returns_expected_shape() -> None:
    result = predict_impact("ZONE A", proposed_cooling_setpoint_c=25.0, proposed_heating_setpoint_c=None)
    assert "predicted_kw_delta" in result
    assert "predicted_pmv" in result
    assert "comfort_status" in result
    assert "explanation" in result
    assert isinstance(result["explanation"], str) and len(result["explanation"]) > 0


def test_raising_cooling_setpoint_reduces_predicted_load() -> None:
    # A higher (warmer) cooling setpoint should draw less or equal power
    # projected forward than a colder one, all else equal.
    warm = predict_impact("ZONE A", proposed_cooling_setpoint_c=26.0, proposed_heating_setpoint_c=None)
    cold = predict_impact("ZONE A", proposed_cooling_setpoint_c=21.0, proposed_heating_setpoint_c=None)
    assert warm["predicted_kw_delta"] <= cold["predicted_kw_delta"]


def test_comfort_status_labels() -> None:
    comfortable = predict_impact("ZONE A", proposed_cooling_setpoint_c=23.0, proposed_heating_setpoint_c=None)
    assert comfortable["comfort_status"] in ("comfortable", "slightly uncomfortable", "uncomfortable")
