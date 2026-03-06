from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import requests

from ..types import TripConfig, WeatherSummary


class WeatherFallbackError(RuntimeError):
    pass


def fetch_fallback_weather(config: TripConfig, session: requests.Session | None = None) -> tuple[WeatherSummary, dict[str, Any]]:
    if config.latitude is None or config.longitude is None:
        raise WeatherFallbackError("Fallback weather requires coordinates")

    session = session or requests.Session()
    params = {
        "latitude": config.latitude,
        "longitude": config.longitude,
        "daily": "temperature_2m_min,temperature_2m_max,snowfall_sum,wind_speed_10m_max",
        "timezone": "UTC",
    }
    resp = session.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    daily = data.get("daily", {})

    summary = WeatherSummary(
        source="open-meteo",
        source_status="fallback",
        fetch_timestamp=datetime.now(UTC).isoformat(),
        headline="Fallback weather forecast",
        snow_total_cm=_pick_first_number(daily.get("snowfall_sum"), scale=1.0),
        temp_min_c=_pick_first_number(daily.get("temperature_2m_min"), scale=1.0),
        temp_max_c=_pick_first_number(daily.get("temperature_2m_max"), scale=1.0),
        wind_ridge_kmh=_pick_first_number(daily.get("wind_speed_10m_max"), scale=1.0),
        freezing_level_m=None,
        confidence_note="Fallback weather source",
        raw_excerpt=str(data)[:500],
        details={"keys": sorted(data.keys())},
    )
    return summary, data


def _pick_first_number(values: Any, scale: float = 1.0) -> float | None:
    if isinstance(values, list) and values:
        try:
            return float(values[0]) * scale
        except (TypeError, ValueError):
            return None
    return None