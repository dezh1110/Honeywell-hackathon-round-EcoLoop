from app.agent.recommendations import RecommendationEngine
from app.config import settings
from app.telemetry.models import Telemetry, ZoneReading


def make_telemetry(carbon: float, avg_temp: float = 23.0, optimized_kw: float = 5.0,
                    iaq_ppm: float = 420.0) -> Telemetry:
    return Telemetry(
        sim_time="07/26 17:00:00",
        baseline_kw=10.0,
        optimized_kw=optimized_kw,
        grid_carbon_intensity=carbon,
        indoor_air_quality_ppm=iaq_ppm,
        zones=[ZoneReading(zone="ZONE A", air_temp_c=avg_temp)],
    )


def test_carbon_peak_warning_fires_once() -> None:
    engine = RecommendationEngine()
    msgs = engine.check(make_telemetry(420), sim_hour=17)
    assert len(msgs) == 1
    assert "carbon" in msgs[0].lower()

    # Same conditions next cycle -> no duplicate warning.
    msgs_again = engine.check(make_telemetry(420), sim_hour=17)
    assert msgs_again == []


def test_carbon_peak_warning_does_not_fire_outside_peak_hours() -> None:
    engine = RecommendationEngine()
    msgs = engine.check(make_telemetry(420), sim_hour=10)
    assert msgs == []


def test_override_frequency_warning() -> None:
    engine = RecommendationEngine()
    for _ in range(3):
        engine.note_action_source("ZONE B", "safety_clamp")
    msgs = engine.check(make_telemetry(300), sim_hour=10)
    assert any("ZONE B" in m for m in msgs)

    # Doesn't repeat once issued.
    msgs_again = engine.check(make_telemetry(300), sim_hour=10)
    assert not any("ZONE B" in m for m in msgs_again)


def test_extreme_temperature_warning() -> None:
    engine = RecommendationEngine()
    msgs = engine.check(make_telemetry(300, avg_temp=30.0), sim_hour=10)
    assert any("outside the normal comfort band" in m for m in msgs)


def test_peak_demand_warning_fires_once() -> None:
    engine = RecommendationEngine()
    over_threshold = settings.peak_demand_threshold_kw + 1.0
    msgs = engine.check(make_telemetry(300, optimized_kw=over_threshold), sim_hour=10)
    assert any("peak demand threshold" in m for m in msgs)

    msgs_again = engine.check(make_telemetry(300, optimized_kw=over_threshold), sim_hour=10)
    assert not any("peak demand threshold" in m for m in msgs_again)

    # Drops back under threshold -> warning can fire again next time it's exceeded.
    engine.check(make_telemetry(300, optimized_kw=1.0), sim_hour=10)
    msgs_third = engine.check(make_telemetry(300, optimized_kw=over_threshold), sim_hour=10)
    assert any("peak demand threshold" in m for m in msgs_third)


def test_iaq_warning() -> None:
    engine = RecommendationEngine()
    msgs = engine.check(make_telemetry(300, iaq_ppm=1200.0), sim_hour=10)
    assert any("indoor CO2" in m for m in msgs)

    # Doesn't repeat while still elevated.
    msgs_again = engine.check(make_telemetry(300, iaq_ppm=1200.0), sim_hour=10)
    assert not any("indoor CO2" in m for m in msgs_again)
