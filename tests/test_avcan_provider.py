from __future__ import annotations

import json
from pathlib import Path

import pytest

from inreach_bot.providers.avcan import (
    AvalancheProviderError,
    extract_d_plus_1_numeric_from_report,
    normalize_avalanche_summary,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_extract_d_plus_1_numeric_from_report_with_numeric_values():
    report = _load("avcan_report_numeric.json")
    ratings = extract_d_plus_1_numeric_from_report(report)
    assert ratings == {"alp": 4, "tln": 3, "btl": 3}


def test_extract_d_plus_1_numeric_from_report_with_word_values():
    report = _load("avcan_report_words.json")
    ratings = extract_d_plus_1_numeric_from_report(report)
    assert ratings == {"alp": 3, "tln": 2, "btl": 1}


def test_extract_d_plus_1_missing_elevation_raises():
    report = _load("avcan_report_missing_btl.json")
    with pytest.raises(AvalancheProviderError, match="missing elevations"):
        extract_d_plus_1_numeric_from_report(report)


def test_extract_d_plus_1_empty_day_list_raises():
    report = {"dangerRatings": []}
    with pytest.raises(AvalancheProviderError, match="day list"):
        extract_d_plus_1_numeric_from_report(report)


def test_extract_d_plus_1_unknown_label_raises():
    report = _load("avcan_report_unknown_label.json")
    with pytest.raises(AvalancheProviderError, match="Unknown danger rating label"):
        extract_d_plus_1_numeric_from_report(report)


def test_normalize_avalanche_summary_populates_compact_details():
    report = _load("avcan_report_numeric.json")
    summary = normalize_avalanche_summary("Rogers Pass", report)
    assert summary.danger_ratings_by_elevation == {"alp": "4", "tln": "3", "btl": "3"}
    assert summary.details["d_plus_1_compact"] == "4/3/3"
    assert summary.primary_problem is None