"""Grid carbon-intensity lookup, used as a reasoning input for the agent."""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger("ecoloop.carbon")

_cache: dict[str, tuple[float, float]] = {}  # zone -> (value, fetched_at_epoch)
_CACHE_TTL_S = 300


def _static_estimate(now: datetime | None = None) -> float:
    """Deterministic diurnal curve (gCO2/kWh) used when no live API key is set.

    Mirrors a typical grid: cleaner overnight (more baseload/hydro/wind),
    dirtier during the evening peak when fast-ramping thermal plants cover
    demand. Good enough for a PoC reasoning input without external calls.
    """
    now = now or datetime.now(timezone.utc)
    hour = now.hour + now.minute / 60.0
    base = 380.0
    swing = 90.0 * math.sin((hour - 6) / 24 * 2 * math.pi)
    return round(base + swing, 1)


def get_grid_carbon_intensity() -> float:
    zone = settings.carbon_intensity_zone
    cached = _cache.get(zone)
    if cached and (time.time() - cached[1]) < _CACHE_TTL_S:
        return cached[0]

    if settings.carbon_intensity_provider == "electricitymaps" and settings.carbon_intensity_api_key:
        try:
            resp = httpx.get(
                "https://api.electricitymap.org/v3/carbon-intensity/latest",
                params={"zone": zone},
                headers={"auth-token": settings.carbon_intensity_api_key},
                timeout=5.0,
            )
            resp.raise_for_status()
            value = float(resp.json()["carbonIntensity"])
            _cache[zone] = (value, time.time())
            return value
        except Exception:  # noqa: BLE001
            logger.exception("electricitymaps lookup failed, falling back to static estimate")

    value = _static_estimate()
    _cache[zone] = (value, time.time())
    return value
