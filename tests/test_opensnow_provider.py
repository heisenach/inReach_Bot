from __future__ import annotations

import json
from pathlib import Path

from inreach_bot.providers.opensnow import normalize_weather_summary

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalize_weather_summary_from_fixture():
    payload = json.loads((FIXTURES / "opensnow_sample.json").read_text(encoding="utf-8"))
    summary = normalize_weather_summary(payload)
    assert summary.source == "opensnow"
    assert summary.headline == "Snow returns overnight"
    assert summary.snow_total_cm == 18
    assert summary.wind_ridge_kmh == 35