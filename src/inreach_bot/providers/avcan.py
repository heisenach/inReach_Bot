from __future__ import annotations

import re
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

_ALL_ASPECTS = {"n", "ne", "e", "se", "s", "sw", "w", "nw"}

_CONFIDENCE_ABBREV: dict[str, str] = {
    "low": "Low",
    "moderate": "Mod",
    "high": "High",
    "norating": "NR",
    "noRating": "NR",
}

_PROBLEM_TYPE_ABBREV: dict[str, str] = {
    "persistentslab": "PS",
    "stormslab": "SS",
    "windslab": "WS",
    "loosesnowdry": "LS",
    "loosedrynaturalrelease": "LS",
    "loosesnowwet": "LSW",
    "loosewetnaturalrelease": "LSW",
    "cornice": "Cors",
    "wetslab": "WetSl",
    "glideavalanche": "Glide",
}

_LIKELIHOOD_ABBREV: dict[str, str] = {
    "unlikely": "Unlkly",
    "possible": "Pos",
    "likely": "Lkly",
    "verylikely": "VLkly",
    "almostcertain": "Cer",
    "certain": "Cer",
}

# Applied in order — longer phrases first to avoid partial matches
_WIND_REPLACEMENTS: list[tuple[str, str]] = [
    ("very strong", "VStr"),
    ("gusty moderate", "GstMod"),
    ("gusty", "Gst"),
    ("light", "Lt"),
    ("moderate", "Mod"),
    ("strong", "Str"),
    ("calm", "Calm"),
]

_FILLER_PATTERNS: list[str] = [
    r"freezing level \(fzl\)",
    r"freezing level",
    r"\balpine\b",
]


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
        # The point endpoint wraps the report under point.report
        report = point_data.get("point", {}).get("report") if isinstance(point_data, dict) else None
    if not isinstance(report, dict):
        raise AvalancheProviderError("Point response missing report object")

    summary = normalize_avalanche_summary(report=report)
    raw = {
        "point": point_data,
        "resolved_from": {"lat": config.latitude, "lon": config.longitude},
    }
    return summary, raw


def normalize_avalanche_summary(report: dict[str, Any]) -> AvalancheSummary:
    d1_numeric = extract_d_plus_1_numeric_from_report(report)
    d1_compact = f"{d1_numeric['alp']}/{d1_numeric['tln']}/{d1_numeric['btl']}"

    return AvalancheSummary(
        source_status="ok",
        fetch_timestamp=datetime.now(UTC).isoformat(),
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
            "date_issued": _parse_date_issued(report),
            "confidence": _parse_confidence(report),
            "problems": _parse_problems(report),
            "wx": _parse_weather_wx(report),
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


def extract_claude_text_payload(report: dict[str, Any]) -> str:
    """Build a plain-text blob for Claude from the descriptive fields of the report.

    Skips weather-summary (weather is already in the base message) and skips
    structured data like danger ratings (also in base message). Strips HTML.
    """
    parts: list[str] = []

    highlights = report.get("highlights")
    if highlights:
        parts.append(_strip_html(highlights))

    for summary in report.get("summaries", []):
        stype = summary.get("type", {}).get("value", "")
        if stype == "weather-summary":
            continue
        content = summary.get("content", "")
        if content:
            parts.append(_strip_html(content))

    confidence = report.get("confidence", {})
    for stmt in confidence.get("statements", []):
        if stmt:
            parts.append(stmt)

    for problem in report.get("problems", []):
        comment = problem.get("comment", "")
        if comment:
            parts.append(_strip_html(comment))

    return " ".join(p.strip() for p in parts if p.strip())


# ---------------------------------------------------------------------------
# Private helpers — new parsing functions
# ---------------------------------------------------------------------------

def _parse_date_issued(report: dict[str, Any]) -> str | None:
    raw = report.get("dateIssued") or report.get("validFrom")
    if not raw:
        return None
    # Expect ISO 8601 like "2026-03-05T00:00:00Z"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%m-%d")
    except (ValueError, AttributeError):
        return None


def _parse_confidence(report: dict[str, Any]) -> str | None:
    try:
        value = report["confidence"]["rating"]["value"]
    except (KeyError, TypeError):
        return None
    if not value:
        return None
    return _CONFIDENCE_ABBREV.get(value, _CONFIDENCE_ABBREV.get(value.lower(), value.capitalize()))


def _parse_problems(report: dict[str, Any]) -> list[dict[str, str]]:
    raw_problems = report.get("problems", [])
    if not isinstance(raw_problems, list):
        return []
    result = []
    for prob in raw_problems:
        if not isinstance(prob, dict):
            continue
        ptype = _abbrev_problem_type(prob.get("type", {}).get("value", ""))
        data = prob.get("data", {})
        elevations = _elevation_bitmask(data.get("elevations", []))
        aspects = _format_aspects(data.get("aspects", []))
        likelihood = _abbrev_likelihood(data.get("likelihood", {}).get("value", ""))
        size_min = _fmt_size(data.get("expectedSize", {}).get("min", ""))
        size_max = _fmt_size(data.get("expectedSize", {}).get("max", ""))
        size = f"{size_min}-{size_max}" if size_min and size_max else size_min or size_max or "?"
        result.append({
            "type": ptype,
            "elevations": elevations,
            "aspects": aspects,
            "likelihood": likelihood,
            "size": size,
        })
    return result


def _abbrev_problem_type(raw: str) -> str:
    key = re.sub(r"[\s_\-]", "", raw).lower()
    return _PROBLEM_TYPE_ABBREV.get(key, raw[:6] if raw else "?")


def _abbrev_likelihood(raw: str) -> str:
    key = re.sub(r"[\s_\-]", "", raw).lower()
    return _LIKELIHOOD_ABBREV.get(key, raw.capitalize() if raw else "?")


def _format_aspects(aspects_list: list[dict[str, Any]]) -> str:
    values = {a.get("value", "").lower() for a in aspects_list if isinstance(a, dict)}
    if values >= _ALL_ASPECTS:
        return "ALL"
    order = ["n", "ne", "e", "se", "s", "sw", "w", "nw"]
    return ",".join(v.upper() for v in order if v in values)


def _elevation_bitmask(elevations_list: list[dict[str, Any]]) -> str:
    """Return alp-tln-btl bitmask, e.g. '1-1-0'."""
    values = {e.get("value", "").lower() for e in elevations_list if isinstance(e, dict)}
    alp = "1" if values & {"alp", "alpine", "upper"} else "0"
    tln = "1" if values & {"tln", "treeline", "tree_line"} else "0"
    btl = "1" if values & {"btl", "belowtreeline", "below_tree_line", "belowTreeline".lower()} else "0"
    return f"{alp}-{tln}-{btl}"


def _fmt_size(value: str) -> str:
    """Format size value: strip trailing '.0' for clean display (e.g. '4.0' → '4')."""
    try:
        f = float(value)
        return str(int(f)) if f == int(f) else str(f)
    except (ValueError, TypeError):
        return value


def _parse_weather_wx(report: dict[str, Any]) -> list[dict[str, str]]:
    """Extract tonight and next-day weather as abbreviated label/text dicts."""
    wx_content = ""
    for summary in report.get("summaries", []):
        if isinstance(summary, dict) and summary.get("type", {}).get("value") == "weather-summary":
            wx_content = summary.get("content", "")
            break
    if not wx_content:
        return []

    # Split only on paragraph-level <strong> tags (i.e. <p><strong>Day Label</strong>...)
    # This avoids splitting on inline <strong>°</strong> within a forecast line.
    chunks = re.split(r"<p>\s*<strong>(.*?)</strong>", wx_content)
    # chunks[0] = preamble (discard), then alternating: label, rest-of-paragraph, ...
    result = []
    i = 1
    while i + 1 < len(chunks) and len(result) < 2:
        label_raw = chunks[i].strip()
        content_raw = chunks[i + 1]
        i += 2
        if not label_raw:
            continue
        label = _normalize_wx_label(label_raw)
        text = _abbreviate_wx_text(content_raw)
        if text:
            result.append({"label": label, "text": text})
    return result


def _normalize_wx_label(raw: str) -> str:
    clean = re.sub(r"\s+", " ", raw).strip().rstrip(".")
    lower = clean.lower()
    if "tonight" in lower or "tonite" in lower:
        return "Tnite"
    day_map = {
        "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed",
        "thursday": "Thu", "friday": "Fri", "saturday": "Sat", "sunday": "Sun",
        "mon": "Mon", "tue": "Tue", "wed": "Wed",
        "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun",
    }
    for key, abbrev in day_map.items():
        if lower.startswith(key):
            return abbrev
    return clean[:6]


def _abbreviate_wx_text(raw: str) -> str:
    text = _strip_html(raw).strip().strip(".")

    # Temp: "Low -6°C" / "High -5°C" / "Low -6 ° C" (inline <strong>°</strong> stripped) → "-6C"
    # Combined: "Low -9°C, High -7°C" → "-9/-7C"
    _DEG = r"\s*°?\s*"  # optional degree sign with surrounding spaces
    text = re.sub(
        rf"[Ll]ow\s*([+-]?\d+){_DEG}C,?\s*[Hh]igh\s*([+-]?\d+){_DEG}C",
        lambda m: f"{m.group(1)}/{m.group(2)}C",
        text,
    )
    text = re.sub(rf"[Hh]igh\s*([+-]?\d+){_DEG}C", lambda m: f"{m.group(1)}C", text)
    text = re.sub(rf"[Ll]ow\s*([+-]?\d+){_DEG}C", lambda m: f"{m.group(1)}C", text)
    text = re.sub(rf"([+-]?\d+){_DEG}C\b", lambda m: f"{m.group(1)}C", text)

    # FZL: "Freezing level (FZL) 1300m" or "FZL 1500m" → "FZL1300"
    text = re.sub(r"[Ff]reezing\s+[Ll]evel\s*\(FZL\)\s*(\d+)\s*m", r"FZL\1", text)
    text = re.sub(r"\bFZL\s+(\d+)\s*m", r"FZL\1", text)

    # Wind qualifiers (case-insensitive, longest first)
    for phrase, abbrev in _WIND_REPLACEMENTS:
        text = re.sub(r"\b" + re.escape(phrase) + r"\b", abbrev, text, flags=re.IGNORECASE)

    # Strip filler words
    for pattern in _FILLER_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Collapse whitespace and punctuation
    text = re.sub(r"\s*\.\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip().strip(".")
    return text


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Original private helpers (unchanged)
# ---------------------------------------------------------------------------

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


def _extract_first_text(detail: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = detail.get(key)
        if value:
            return str(value)
    return None
