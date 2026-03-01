from __future__ import annotations

from dataclasses import dataclass

from ..types import AvalancheSummary, WeatherSummary


@dataclass(slots=True)
class MessageBundle:
    combined: str
    weather_only: str
    avalanche_only: str


PRIORITY_FIELDS = ["danger", "wind", "temp", "snow", "advice"]


def build_messages(weather: WeatherSummary, avalanche: AvalancheSummary) -> MessageBundle:
    weather_msg = (
        f"WX [{weather.source_status}] {weather.headline} | "
        f"Snow:{_fmt_num(weather.snow_total_cm, 'cm')} "
        f"Temp:{_fmt_num(weather.temp_min_c, 'C')}/{_fmt_num(weather.temp_max_c, 'C')} "
        f"Wind:{_fmt_num(weather.wind_ridge_kmh, 'km/h')} "
        f"Freeze:{_fmt_num(weather.freezing_level_m, 'm')}"
    ).strip()

    danger_str = ", ".join(f"{k}:{v}" for k, v in avalanche.danger_ratings_by_elevation.items()) or "unknown"
    avalanche_msg = (
        f"AVL [{avalanche.source_status}] {avalanche.region_name} | "
        f"Danger:{danger_str} "
        f"P1:{avalanche.primary_problem or 'n/a'} "
        f"P2:{avalanche.secondary_problem or 'n/a'} "
        f"Advice:{(avalanche.travel_advice or 'n/a')[:180]}"
    ).strip()

    combined = f"{weather_msg} || {avalanche_msg}"
    return MessageBundle(combined=combined, weather_only=weather_msg, avalanche_only=avalanche_msg)


def build_avalanche_only_message(avalanche: AvalancheSummary) -> str:
    return format_d_plus_1_numeric(avalanche)


def format_d_plus_1_numeric(avalanche: AvalancheSummary) -> str:
    alp = avalanche.danger_ratings_by_elevation.get("alp")
    tln = avalanche.danger_ratings_by_elevation.get("tln")
    btl = avalanche.danger_ratings_by_elevation.get("btl")
    if not (alp and tln and btl):
        raise ValueError("Missing required D+1 ratings for alp/tln/btl")
    return f"D+1 A/T/B: {alp}/{tln}/{btl}"


def choose_outbound_messages(bundle: MessageBundle, max_chars: int) -> list[str]:
    if len(bundle.combined) <= max_chars:
        return [bundle.combined]

    weather_msg = _truncate(bundle.weather_only, max_chars)
    avalanche_msg = _truncate(bundle.avalanche_only, max_chars)
    return [weather_msg, avalanche_msg]


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    suffix = " [truncated]"
    if max_chars <= len(suffix):
        return text[:max_chars]
    return text[: max_chars - len(suffix)] + suffix


def _fmt_num(value: float | None, unit: str) -> str:
    if value is None:
        return f"n/a{unit}"
    if value.is_integer():
        return f"{int(value)}{unit}"
    return f"{value:.1f}{unit}"
