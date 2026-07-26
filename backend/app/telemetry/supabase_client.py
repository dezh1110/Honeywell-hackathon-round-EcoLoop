"""
Thin write-side client to the same Supabase project the React dashboard reads
from. The backend uses the *service role* key (server-side only, never shipped
to the browser) so it can insert rows regardless of RLS policy, while the
frontend keeps using its anon key for read-only realtime subscriptions.

If Supabase isn't configured, every call becomes a structured log line instead
of raising — the agent loop must keep running even if telemetry storage is
temporarily unavailable.
"""
from __future__ import annotations

import logging
from typing import Optional

from supabase import Client, create_client

from app.config import settings
from app.telemetry.models import BuildingLog, ControlAction, Telemetry

logger = logging.getLogger("ecoloop.supabase")


class SupabaseSink:
    def __init__(self) -> None:
        self._client: Optional[Client] = None
        if settings.supabase_url and settings.supabase_service_key:
            self._client = create_client(settings.supabase_url, settings.supabase_service_key)
        else:
            logger.warning(
                "SUPABASE_URL / SUPABASE_SERVICE_KEY not set — telemetry will only be logged locally."
            )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def write_log(self, log: BuildingLog, reasoning_trace: Optional[list[dict]] = None) -> None:
        payload = {
            "created_at": log.created_at.isoformat(),
            "event_type": log.event_type,
            "message": log.message,
            "severity": log.severity,
            "zone": log.zone,
            "metric_value": log.metric_value,
            "reasoning_trace": reasoning_trace or [],
        }
        if not self._client:
            logger.info("building_log: %s", payload)
            return
        try:
            self._client.table("building_logs").insert(payload).execute()
        except Exception:  # noqa: BLE001 - never let a network hiccup kill the control loop
            logger.exception("Failed to write building_log")

    def write_telemetry(self, telemetry: Telemetry) -> None:
        payload = {
            "created_at": telemetry.timestamp.isoformat(),
            "sim_time": telemetry.sim_time,
            "baseline_kw": telemetry.baseline_kw,
            "optimized_kw": telemetry.optimized_kw,
            "grid_carbon_intensity": telemetry.grid_carbon_intensity,
            "indoor_air_quality_ppm": telemetry.indoor_air_quality_ppm,
            "avg_zone_temp": round(telemetry.avg_zone_temp, 2),
            "zones": [z.model_dump() for z in telemetry.zones],
        }
        if not self._client:
            logger.info("telemetry: %s", payload)
            return
        try:
            self._client.table("building_telemetry").insert(payload).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write telemetry")

    def write_control_action(self, action: ControlAction) -> None:
        payload = {
            "created_at": action.timestamp.isoformat(),
            "zone": action.zone,
            "cooling_setpoint_c": action.cooling_setpoint_c,
            "heating_setpoint_c": action.heating_setpoint_c,
            "reason": action.reason,
            "source": action.source,
        }
        if not self._client:
            logger.info("control_action: %s", payload)
            return
        try:
            self._client.table("control_actions").insert(payload).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write control_action")

    def fetch_pending_overrides(self) -> list[dict]:
        """Manual setpoint overrides submitted from the dashboard's Control Panel."""
        if not self._client:
            return []
        try:
            resp = (
                self._client.table("control_overrides")
                .select("*")
                .eq("applied", False)
                .order("created_at", desc=False)
                .execute()
            )
            return resp.data or []
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch control_overrides")
            return []

    def mark_override_applied(self, override_id: str) -> None:
        if not self._client:
            return
        try:
            self._client.table("control_overrides").update({"applied": True}).eq(
                "id", override_id
            ).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to mark override applied")

    # -- NLP Insights panel ---------------------------------------------
    def fetch_pending_nlp_queries(self) -> list[dict]:
        if not self._client:
            return []
        try:
            resp = (
                self._client.table("nlp_queries")
                .select("*")
                .eq("status", "pending")
                .order("created_at", desc=False)
                .execute()
            )
            return resp.data or []
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch nlp_queries")
            return []

    def write_nlp_answer(self, query_id: str, answer: str, reasoning_trace: list[dict]) -> None:
        if not self._client:
            logger.info("nlp_answer[%s]: %s", query_id, answer)
            return
        try:
            self._client.table("nlp_queries").update(
                {"answer": answer, "reasoning_trace": reasoning_trace, "status": "answered"}
            ).eq("id", query_id).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write nlp_queries answer")

    def mark_nlp_query_error(self, query_id: str, message: str) -> None:
        if not self._client:
            return
        try:
            self._client.table("nlp_queries").update(
                {"answer": message, "status": "error"}
            ).eq("id", query_id).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to mark nlp_queries error")

    # -- What-If Simulator ------------------------------------------------
    def fetch_pending_whatif_requests(self) -> list[dict]:
        if not self._client:
            return []
        try:
            resp = (
                self._client.table("whatif_requests")
                .select("*")
                .eq("status", "pending")
                .order("created_at", desc=False)
                .execute()
            )
            return resp.data or []
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch whatif_requests")
            return []

    def write_whatif_result(self, request_id: str, result: dict) -> None:
        if not self._client:
            logger.info("whatif_result[%s]: %s", request_id, result)
            return
        try:
            self._client.table("whatif_requests").update(
                {**result, "status": "done"}
            ).eq("id", request_id).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write whatif_requests result")

    def mark_whatif_error(self, request_id: str, message: str) -> None:
        if not self._client:
            return
        try:
            self._client.table("whatif_requests").update(
                {"explanation": message, "status": "error"}
            ).eq("id", request_id).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to mark whatif_requests error")


sink = SupabaseSink()
