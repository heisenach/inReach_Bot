from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class TripConfig:
    start_date: date
    end_date: date
    send_time_gst: str
    gst_utc_offset: str
    latitude: float | None
    longitude: float | None
    avcan_region_mode: str
    avcan_region_value: str
    opensnow_target_mode: str
    opensnow_lat: float | None
    opensnow_lon: float | None
    opensnow_point_id: str | None
    mapshare_url: str
    opensnow_auth_secret_name: str | None
    preview_only: bool = True
    message_max_chars: int = 160
    send_tolerance_minutes: int = 20


@dataclass(slots=True)
class WeatherSummary:
    source: str
    source_status: str
    fetch_timestamp: str
    headline: str
    snow_total_cm: float | None = None
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    wind_ridge_kmh: float | None = None
    freezing_level_m: float | None = None
    confidence_note: str | None = None
    raw_excerpt: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AvalancheSummary:
    source_status: str
    fetch_timestamp: str
    danger_ratings_by_elevation: dict[str, str]
    primary_problem: str | None
    secondary_problem: str | None
    travel_advice: str | None
    valid_from: str | None
    valid_to: str | None
    source_url: str | None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SendDecision:
    eligible_now: bool
    reason: str
    idempotency_key: str
