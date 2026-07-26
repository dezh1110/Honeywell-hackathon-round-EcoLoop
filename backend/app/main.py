"""
Entrypoint that wires the closed loop together:

    EnergyPlus (or mock RC model)
        --telemetry-->  decision callback
        --error log-->  decision callback
    decision callback:
        publish telemetry+errors to shared_state (-> Supabase `building_telemetry`)
        run_reasoning_cycle()  [ReAct agent, calls MCP tools in-process]
        log the agent's summary + full tool-call trace to Supabase `building_logs`
        run the recommendation heuristics and log any new proactive alerts
        poll & answer any pending NLP Insights questions
        poll & compute any pending What-If Simulator requests
        consume the pending action (if any) and hand it back to the simulator,
        which forward-injects it via an EMS actuator (real EnergyPlus) or
        the model's own setpoint field (mock)

Run with:  python -m app.main
"""
from __future__ import annotations

import logging
import re
import signal
import sys
import threading
import time
from typing import Optional

from app.agent.react_agent import answer_nlp_question, run_reasoning_cycle
from app.agent.recommendations import recommendation_engine
from app.agent.whatif import predict_impact
from app.config import settings
from app.telemetry import shared_state
from app.telemetry.carbon import get_grid_carbon_intensity
from app.telemetry.models import BuildingLog, ControlAction, Telemetry
from app.telemetry.supabase_client import sink

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("ecoloop.main")

_SIM_HOUR_RE = re.compile(r"(\d{1,2}):\d{2}:\d{2}\s*$")


def _extract_hour(sim_time: str) -> int:
    match = _SIM_HOUR_RE.search(sim_time)
    return int(match.group(1)) if match else 12


def make_decision(telemetry: Telemetry, error_summary: str) -> Optional[ControlAction]:
    telemetry.grid_carbon_intensity = get_grid_carbon_intensity()
    shared_state.publish_telemetry(telemetry)

    logger.info(
        "[%s] baseline=%.2fkW optimized=%.2fkW avg_zone_temp=%.1fC carbon=%.0fgCO2/kWh",
        telemetry.sim_time, telemetry.baseline_kw, telemetry.optimized_kw,
        telemetry.avg_zone_temp, telemetry.grid_carbon_intensity,
    )

    try:
        summary, trace = run_reasoning_cycle(telemetry.sim_time, error_summary)
    except Exception:  # noqa: BLE001
        logger.exception("Reasoning cycle failed; holding current setpoints")
        sink.write_log(
            BuildingLog(
                event_type="error",
                severity="warning",
                message="Agent reasoning cycle failed (LLM endpoint unreachable?); holding setpoints.",
            )
        )
        return None

    sink.write_log(
        BuildingLog(
            event_type="system",
            severity="info",
            message=summary,
            metric_value=telemetry.grid_carbon_intensity,
        ),
        reasoning_trace=trace,
    )

    run_recommendation_checks(telemetry)

    action = shared_state.consume_pending_action()
    if action is not None:
        recommendation_engine.note_action_source(action.zone, action.source)
    return action


def run_recommendation_checks(telemetry: Telemetry) -> None:
    sim_hour = _extract_hour(telemetry.sim_time)
    for message in recommendation_engine.check(telemetry, sim_hour):
        logger.info("Recommendation: %s", message)
        sink.write_log(
            BuildingLog(event_type="recommendation", severity="warning", message=message)
        )


def apply_pending_manual_overrides() -> None:
    for row in sink.fetch_pending_overrides():
        shared_state.propose_action(
            zone=row.get("zone", "ZONE A"),
            cooling_setpoint_c=row.get("cooling_setpoint_c"),
            heating_setpoint_c=row.get("heating_setpoint_c"),
            reason="Manual override from dashboard control panel.",
            source="manual_override",
        )
        sink.mark_override_applied(row["id"])


def answer_pending_nlp_questions() -> None:
    for row in sink.fetch_pending_nlp_queries():
        try:
            answer, trace = answer_nlp_question(row["question"])
            sink.write_nlp_answer(row["id"], answer, trace)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to answer NLP query %s", row.get("id"))
            sink.mark_nlp_query_error(row["id"], f"Couldn't answer that question: {exc}")


def compute_pending_whatif_requests() -> None:
    for row in sink.fetch_pending_whatif_requests():
        try:
            result = predict_impact(
                zone=row["zone"],
                proposed_cooling_setpoint_c=row.get("proposed_cooling_setpoint_c"),
                proposed_heating_setpoint_c=row.get("proposed_heating_setpoint_c"),
            )
            sink.write_whatif_result(row["id"], result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to compute what-if request %s", row.get("id"))
            sink.mark_whatif_error(row["id"], f"Couldn't project that scenario: {exc}")


FAST_POLL_INTERVAL_SECONDS = 4
NLP_POLL_INTERVAL_SECONDS = 4


def poll_fast_dashboard_requests(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            apply_pending_manual_overrides()
            compute_pending_whatif_requests()
        except Exception:  # noqa: BLE001
            logger.exception("Fast dashboard request poller hit an unexpected error")
        stop_event.wait(FAST_POLL_INTERVAL_SECONDS)


def poll_nlp_questions(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            answer_pending_nlp_questions()
        except Exception:  # noqa: BLE001
            logger.exception("NLP question poller hit an unexpected error")
        stop_event.wait(NLP_POLL_INTERVAL_SECONDS)


def start_background_pollers() -> threading.Event:
    stop_event = threading.Event()
    threading.Thread(
        target=poll_fast_dashboard_requests, args=(stop_event,), daemon=True,
        name="ecoloop-fast-poller",
    ).start()
    threading.Thread(
        target=poll_nlp_questions, args=(stop_event,), daemon=True,
        name="ecoloop-nlp-poller",
    ).start()
    logger.info(
        "Dashboard request pollers started: fast (What-If Simulator + manual overrides, "
        "every %ds) and NLP Insights (every %ds, its own thread)",
        FAST_POLL_INTERVAL_SECONDS, NLP_POLL_INTERVAL_SECONDS,
    )
    return stop_event


def run() -> int:
    logger.info("EcoLoop backend starting (simulation_backend=%s)", settings.simulation_backend)

    poller_stop_event = start_background_pollers()

    if settings.simulation_backend == "energyplus":
        from app.energyplus.baseline_runner import BaselineRunner  # noqa: PLC0415
        from app.energyplus.runtime import EnergyPlusRuntime  # noqa: PLC0415

        baseline = BaselineRunner()
        logger.info("Running baseline (unactuated) simulation before starting the live agent loop...")
        baseline.run()
        runtime = EnergyPlusRuntime(decision_fn=make_decision, baseline=baseline)
    else:
        from app.energyplus.mock_runtime import MockRuntime  # noqa: PLC0415

        runtime = MockRuntime(decision_fn=make_decision)
        logger.warning(
            "Running the MOCK RC thermal model, not real EnergyPlus. "
            "Set SIMULATION_BACKEND=energyplus once EnergyPlus is installed. See README."
        )

    def _handle_sigterm(signum, frame):  # noqa: ANN001, ARG001
        logger.info("Shutdown signal received, stopping simulation...")
        poller_stop_event.set()
        runtime.stop()

    signal.signal(signal.SIGINT, _handle_sigterm)
    signal.signal(signal.SIGTERM, _handle_sigterm)

    return runtime.run()


if __name__ == "__main__":
    sys.exit(run())
