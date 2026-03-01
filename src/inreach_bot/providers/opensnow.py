from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import requests

from ..types import TripConfig, WeatherSummary


class OpenSnowProviderError(RuntimeError):
    pass


def fetch_opensnow_summary(
    config: TripConfig,
    auth_payload: dict[str, Any],
    session: requests.Session | None = None,
) -> tuple[WeatherSummary, dict[str, Any]]:
    session = session or requests.Session()
    _apply_auth(session, auth_payload)

    base_url = str(auth_payload.get("base_url", "https://api.opensnow.com")).rstrip("/")
    coordinates_path = str(auth_payload.get("coordinates_path", "/v1/forecast/point"))
    point_path = str(auth_payload.get("point_path", "/v1/forecast/point/{point_id}"))

    if config.opensnow_target_mode == "coordinates":
        if config.opensnow_lat is None or config.opensnow_lon is None:
            raise OpenSnowProviderError("Missing coordinates for opensnow target")
        url = f"{base_url}{coordinates_path}"
        params = {"lat": config.opensnow_lat, "lon": config.opensnow_lon}
    else:
        if not config.opensnow_point_id:
            raise OpenSnowProviderError("Missing point id for opensnow target")
        url = f"{base_url}{point_path.format(point_id=config.opensnow_point_id)}"
        params = None

    response = session.get(url, params=params, timeout=30)
    if response.status_code in {401, 403}:
        raise OpenSnowProviderError("OpenSnow auth failed (401/403)")
    response.raise_for_status()

    raw_payload: dict[str, Any]
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        raw_payload = response.json()
    else:
        raw_payload = {"text": response.text}

    summary = normalize_weather_summary(raw_payload)
    return summary, raw_payload


def normalize_weather_summary(raw_payload: dict[str, Any]) -> WeatherSummary:
    daily = _extract_daily(raw_payload)
    first_day = daily[0] if daily else {}

    headline = (
        _extract_str(first_day, ["headline", "summary", "conditions"]) 
        or _extract_str(raw_payload, ["headline", "summary", "conditions"]) 
        or "OpenSnow forecast"
    )

    summary = WeatherSummary(
        source="opensnow",
        source_status="ok",
        fetch_timestamp=datetime.now(UTC).isoformat(),
        headline=headline,
        snow_total_cm=_extract_num(first_day, ["snow_total_cm", "snowCm", "snow", "snowfall_cm"]),
        temp_min_c=_extract_num(first_day, ["temp_min_c", "tempMinC", "low_c"]),
        temp_max_c=_extract_num(first_day, ["temp_max_c", "tempMaxC", "high_c"]),
        wind_ridge_kmh=_extract_num(first_day, ["wind_ridge_kmh", "windKmh", "wind_speed_kmh"]),
        freezing_level_m=_extract_num(first_day, ["freezing_level_m", "freezingLevelM"]),
        confidence_note=_extract_str(first_day, ["confidence", "confidence_note"]),
        raw_excerpt=str(raw_payload)[:500],
        details={"keys": sorted(raw_payload.keys())},
    )
    return summary


def _apply_auth(session: requests.Session, auth_payload: dict[str, Any]) -> None:
    headers = auth_payload.get("headers", {})
    if isinstance(headers, dict):
        session.headers.update({str(k): str(v) for k, v in headers.items()})

    cookies = auth_payload.get("cookies", {})
    if isinstance(cookies, dict):
        session.cookies.update({str(k): str(v) for k, v in cookies.items()})

    token = auth_payload.get("bearer_token")
    if token:
        session.headers["Authorization"] = f"Bearer {token}"


def _extract_daily(raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("daily", "days", "forecast_days", "forecast"):
        value = raw_payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _extract_str(data: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _extract_num(data: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None