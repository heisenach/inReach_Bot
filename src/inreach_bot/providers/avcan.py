from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import requests

from ..types import AvalancheSummary, TripConfig

BASE_URL = "https://api.avalanche.ca"

_NAME_TO_NUM = {
    "low": 1,
    "moderate": 2,
    "considerable": 3,
    "high": 4,
    "extreme": 5,
}

_ALP_KEYS = ("alp", "alpine", "upper")
_TLN_KEYS = ("tln", "treeline", "tree_line", "treeLine")
_BTL_KEYS = ("btl", "belowtreeline", "below_tree_line", "belowTreeline")


class AvalancheProviderError(RuntimeError):
    pass


def fetch_avalanche_summary(config: TripConfig, session: requests.Session | None = None) -> tuple[AvalancheSummary, dict[str, Any]]:
    session = session or requests.Session()

    if config.latitude is None or config.longitude is None:
        raise AvalancheProviderError("latitude and longitude are required")

    point_url = f"{BASE_URL}/forecasts/en/products/point"
    point_resp = session.get(
        point_url,
        params={"lat": config.latitude, "long": config.longitude},
        timeout=30,
    )
    point_resp.raise_for_status()
    point_data = point_resp.json()

    report = point_data.get("report") if isinstance(point_data, dict) else None
    if not isinstance(report, dict):
        raise AvalancheProviderError("Point response missing report object")

    region_name = _extract_region_name_from_point(point_data) or "Unknown region"
    summary = normalize_avalanche_summary(region_name=region_name, report=report)

    raw = {
        "point": point_data,
        "resolved_from": {"lat": config.latitude, "lon": config.longitude},
    }
    return summary, raw


def normalize_avalanche_summary(region_name: str, report: dict[str, Any]) -> AvalancheSummary:
    d1_numeric = extract_d_plus_1_numeric_from_report(report)
    d1_compact = f"{d1_numeric['alp']}/{d1_numeric['tln']}/{d1_numeric['btl']}"

    return AvalancheSummary(
        source_status="ok",
        fetch_timestamp=datetime.now(UTC).isoformat(),
        region_name=region_name,
        danger_ratings_by_elevation={
            "alp": str(d1_numeric["alp"]),
            "tln": str(d1_numeric["tln"]),
            "btl": str(d1_numeric["btl"]),
        },
        primary_problem=None,
        secondary_problem=None,
        travel_advice=None,
        valid_from=_extract_first_text(report, ["dateIssued", "validFrom"]),
        valid_to=_extract_first_text(report, ["validUntil", "expiresAt"]),
        source_url=_extract_first_text(report, ["url", "link"]),
        details={
            "d_plus_1_numeric": d1_numeric,
            "d_plus_1_compact": d1_compact,
            "raw_report_keys": sorted(report.keys()),
        },
    )


def extract_d_plus_1_numeric_from_report(report: dict[str, Any]) -> dict[str, int]:
    day_list = _find_danger_day_list(report)
    if not day_list:
        raise AvalancheProviderError("report does not contain a danger-ratings day list")

    d_plus_1 = day_list[0]
    if not isinstance(d_plus_1, dict):
        raise AvalancheProviderError("first danger-ratings day entry is not an object")

    rating_source = _extract_rating_source(d_plus_1)

    alp = _extract_elevation_rating(rating_source, _ALP_KEYS)
    tln = _extract_elevation_rating(rating_source, _TLN_KEYS)
    btl = _extract_elevation_rating(rating_source, _BTL_KEYS)

    missing = [name for name, value in (("alp", alp), ("tln", tln), ("btl", btl)) if value is None]
    if missing:
        raise AvalancheProviderError(f"D+1 danger ratings missing elevations: {', '.join(missing)}")

    return {"alp": alp, "tln": tln, "btl": btl}


def _find_danger_day_list(report: dict[str, Any]) -> list[Any]:
    candidate_paths = (
        ("dangerRatings",),
        ("dangerRatingsByDay",),
        ("danger",),
        ("ratings",),
        ("dangerRatings", "days"),
        ("danger", "days"),
        ("danger", "ratings"),
    )

    for path in candidate_paths:
        value = report
        ok = True
        for key in path:
            if not isinstance(value, dict) or key not in value:
                ok = False
                break
            value = value[key]
        if ok and isinstance(value, list):
            return value
    return []


def _extract_rating_source(day_entry: dict[str, Any]) -> Any:
    for key in ("ratings", "dangerRatings", "danger"):
        if key in day_entry:
            return day_entry[key]
    return day_entry


def _extract_elevation_rating(source: Any, keys: tuple[str, ...]) -> int | None:
    if isinstance(source, dict):
        for raw_key, raw_value in source.items():
            normalized_key = str(raw_key).replace("-", "").replace("_", "").lower()
            if normalized_key in {k.lower().replace("_", "") for k in keys}:
                return _rating_to_number(raw_value)

        # Handle nested dicts with explicit elevation field.
        for key, value in source.items():
            if isinstance(value, dict):
                elev = _extract_first_text(value, ["elevation", "level", "name"])
                if elev and elev.lower().replace("_", "") in {k.lower().replace("_", "") for k in keys}:
                    return _rating_to_number(value)

    if isinstance(source, list):
        for item in source:
            if not isinstance(item, dict):
                continue
            elev = _extract_first_text(item, ["elevation", "level", "name", "band"])
            if elev and elev.lower().replace("_", "") in {k.lower().replace("_", "") for k in keys}:
                return _rating_to_number(item)
    return None


def _rating_to_number(value: Any) -> int:
    if isinstance(value, int):
        if 1 <= value <= 5:
            return value
        raise AvalancheProviderError(f"Unsupported numeric danger rating: {value}")

    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            numeric = int(stripped)
            if 1 <= numeric <= 5:
                return numeric
            raise AvalancheProviderError(f"Unsupported numeric danger rating: {stripped}")

        normalized = stripped.casefold()
        if normalized in _NAME_TO_NUM:
            return _NAME_TO_NUM[normalized]
        raise AvalancheProviderError(f"Unknown danger rating label: {value}")

    if isinstance(value, dict):
        for key in ("rating", "value", "danger", "name", "scale"):
            if key in value and value[key] not in (None, ""):
                return _rating_to_number(value[key])

    raise AvalancheProviderError(f"Could not map danger rating value to numeric scale: {value}")


def _extract_region_name_from_point(point_data: Any) -> str | None:
    if isinstance(point_data, dict):
        for key in ("areaName", "name", "region", "area"):
            value = point_data.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                candidate = value.get("name")
                if candidate:
                    return str(candidate)
    elif isinstance(point_data, list) and point_data:
        return _extract_region_name_from_point(point_data[0])
    return None


def _extract_first_text(detail: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = detail.get(key)
        if value:
            return str(value)
    return None