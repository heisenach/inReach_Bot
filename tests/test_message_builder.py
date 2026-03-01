from __future__ import annotations

import pytest

from inreach_bot.formatters.message_builder import (
    build_messages,
    choose_outbound_messages,
    format_d_plus_1_numeric,
)
from inreach_bot.types import AvalancheSummary, WeatherSummary


def sample_weather() -> WeatherSummary:
    return WeatherSummary(
        source="opensnow",
        source_status="ok",
        fetch_timestamp="2026-02-28T00:00:00Z",
        headline="Pow day incoming",
        snow_total_cm=25.0,
        temp_min_c=-10.0,
        temp_max_c=-5.0,
        wind_ridge_kmh=45.0,
        freezing_level_m=1200.0,
    )


def sample_avalanche() -> AvalancheSummary:
    return AvalancheSummary(
        source_status="ok",
        fetch_timestamp="2026-02-28T00:00:00Z",
        region_name="Rogers Pass",
        danger_ratings_by_elevation={"alp": "4", "tln": "3", "btl": "3"},
        primary_problem=None,
        secondary_problem=None,
        travel_advice=None,
        valid_from="2026-02-28",
        valid_to="2026-03-01",
        source_url="https://avalanche.ca",
    )


def test_single_message_when_under_limit():
    bundle = build_messages(sample_weather(), sample_avalanche())
    out = choose_outbound_messages(bundle, max_chars=700)
    assert len(out) == 1


def test_split_and_truncate_when_over_limit():
    bundle = build_messages(sample_weather(), sample_avalanche())
    out = choose_outbound_messages(bundle, max_chars=80)
    assert len(out) == 2
    assert all(len(x) <= 80 for x in out)


def test_format_d_plus_1_numeric():
    msg = format_d_plus_1_numeric(sample_avalanche())
    assert msg == "D+1 A/T/B: 4/3/3"


def test_format_d_plus_1_numeric_requires_all_bands():
    avalanche = sample_avalanche()
    avalanche.danger_ratings_by_elevation.pop("btl")
    with pytest.raises(ValueError, match="alp/tln/btl"):
        format_d_plus_1_numeric(avalanche)