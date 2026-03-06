from __future__ import annotations

from pathlib import Path

from inreach_bot.formatters.verbose_dump import write_preview_artifacts
from inreach_bot.types import AvalancheSummary, WeatherSummary


def test_write_preview_artifacts(tmp_path: Path):
    weather = WeatherSummary(
        source="opensnow",
        source_status="ok",
        fetch_timestamp="2026-02-28T00:00:00Z",
        headline="test",
    )
    avalanche = AvalancheSummary(
        source_status="ok",
        fetch_timestamp="2026-02-28T00:00:00Z",
        danger_ratings_by_elevation={"alp": "Considerable"},
        primary_problem=None,
        secondary_problem=None,
        travel_advice=None,
        valid_from=None,
        valid_to=None,
        source_url=None,
    )

    paths = write_preview_artifacts(
        tmp_path,
        avalanche_raw={"a": 1},
        opensnow_raw={"b": 2},
        avalanche_summary=avalanche,
        weather_summary=weather,
    )

    assert paths["avalanche_raw"].exists()
    assert paths["opensnow_raw"].exists()
    assert paths["weather_verbose"].exists()
    assert paths["avalanche_verbose"].exists()
    assert paths["claude_summary"].exists()
    assert paths["claude_status"].exists()
