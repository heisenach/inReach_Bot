from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .types import SendDecision, TripConfig

TRIP_STATE_DIR = Path(".trip_state")
TRIP_CONFIG_PATH = TRIP_STATE_DIR / "current_trip.json"
LAST_SENT_PATH = TRIP_STATE_DIR / "last_sent.json"

_OFFSET_RE = re.compile(r"^UTC([+-])(\d{2}):(\d{2})$")
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ConfigError(ValueError):
    pass


def _parse_offset(offset_text: str) -> timedelta:
    match = _OFFSET_RE.match(offset_text)
    if not match:
        raise ConfigError("gst_utc_offset must look like UTC-07:00 or UTC+05:30")
    sign, hh, mm = match.groups()
    delta = timedelta(hours=int(hh), minutes=int(mm))
    return -delta if sign == "-" else delta


def _require(value: Any, name: str) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ConfigError(f"Missing required field: {name}")
    return value


def load_trip_config(path: Path = TRIP_CONFIG_PATH) -> TripConfig:
    if not path.exists():
        raise ConfigError(f"Trip config does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))

    send_time_gst = str(_require(payload.get("send_time_gst"), "send_time_gst"))
    if not _TIME_RE.match(send_time_gst):
        raise ConfigError("send_time_gst must be HH:MM in 24h format")

    gst_utc_offset = str(_require(payload.get("gst_utc_offset"), "gst_utc_offset"))
    _parse_offset(gst_utc_offset)

    avcan_region_mode = str(payload.get("avcan_region_mode", "region_name"))
    opensnow_target_mode = str(payload.get("opensnow_target_mode", "coordinates"))

    cfg = TripConfig(
        start_date=datetime.strptime(str(_require(payload.get("start_date"), "start_date")), "%Y-%m-%d").date(),
        end_date=datetime.strptime(str(_require(payload.get("end_date"), "end_date")), "%Y-%m-%d").date(),
        send_time_gst=send_time_gst,
        gst_utc_offset=gst_utc_offset,
        latitude=_to_float(payload.get("latitude", payload.get("avcan_lat"))),
        longitude=_to_float(payload.get("longitude", payload.get("avcan_lon"))),
        avcan_region_mode=avcan_region_mode,
        avcan_region_value=str(payload.get("avcan_region_value", "")),
        opensnow_target_mode=opensnow_target_mode,
        opensnow_lat=_to_float(payload.get("opensnow_lat")),
        opensnow_lon=_to_float(payload.get("opensnow_lon")),
        opensnow_point_id=_to_str_or_none(payload.get("opensnow_point_id")),
        mapshare_url=str(_require(payload.get("mapshare_url"), "mapshare_url")),
        opensnow_auth_secret_name=_to_str_or_none(payload.get("opensnow_auth_secret_name")),
        preview_only=bool(payload.get("preview_only", True)),
        message_max_chars=int(payload.get("message_max_chars", 480)),
        send_tolerance_minutes=int(payload.get("send_tolerance_minutes", 20)),
    )

    if cfg.start_date > cfg.end_date:
        raise ConfigError("start_date must be <= end_date")

    if cfg.latitude is None or cfg.longitude is None:
        raise ConfigError("latitude and longitude are required")

    if cfg.opensnow_target_mode not in {"coordinates", "point_id"}:
        raise ConfigError("opensnow_target_mode must be coordinates or point_id")

    # OpenSnow fields are optional for avalanche-only operation.

    return cfg


def build_send_decision(config: TripConfig, now_utc: datetime | None = None) -> SendDecision:
    now_utc = now_utc or datetime.now(UTC)
    offset = _parse_offset(config.gst_utc_offset)
    local_now = now_utc + offset

    today_local = local_now.date()
    lat = f"{config.latitude:.4f}" if config.latitude is not None else "na"
    lon = f"{config.longitude:.4f}" if config.longitude is not None else "na"
    key = f"{today_local.isoformat()}::{lat},{lon}"

    if config.preview_only:
        return SendDecision(False, "preview_only=true", key)
    if today_local < config.start_date or today_local > config.end_date:
        return SendDecision(False, "outside date window", key)

    target_hour, target_minute = [int(x) for x in config.send_time_gst.split(":")]
    target = local_now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    delta_min = abs((local_now - target).total_seconds()) / 60.0

    if delta_min > config.send_tolerance_minutes:
        return SendDecision(False, "outside send tolerance window", key)

    already_sent = load_last_sent_key()
    if already_sent == key:
        return SendDecision(False, "already sent for this local day", key)

    return SendDecision(True, "eligible", key)


def load_last_sent_key(path: Path = LAST_SENT_PATH) -> str | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _to_str_or_none(payload.get("idempotency_key"))


def persist_last_sent_key(idempotency_key: str, path: Path = LAST_SENT_PATH) -> None:
    TRIP_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"idempotency_key": idempotency_key, "updated_at_utc": datetime.now(UTC).isoformat()}, indent=2),
        encoding="utf-8",
    )


def write_trip_config(payload: dict[str, Any], path: Path = TRIP_CONFIG_PATH) -> None:
    TRIP_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def to_json_dict(config: TripConfig) -> dict[str, Any]:
    data = asdict(config)
    data["start_date"] = config.start_date.isoformat()
    data["end_date"] = config.end_date.isoformat()
    return data


def load_opensnow_auth_from_env() -> dict[str, Any]:
    raw = os.getenv("OPENSNOW_AUTH", "").strip()
    if not raw:
        raise ConfigError("OPENSNOW_AUTH is missing")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError("OPENSNOW_AUTH must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ConfigError("OPENSNOW_AUTH must decode to a JSON object")
    return payload


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _to_str_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
