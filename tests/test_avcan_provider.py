from __future__ import annotations

import json
from pathlib import Path

import pytest

from inreach_bot.providers.avcan import (
    AvalancheProviderError,
    extract_claude_text_payload,
    extract_d_plus_1_numeric_from_report,
    normalize_avalanche_summary,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Existing D+1 extraction tests
# ---------------------------------------------------------------------------

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
    summary = normalize_avalanche_summary(report)
    assert summary.danger_ratings_by_elevation == {"alp": "4", "tln": "3", "btl": "3"}
    assert summary.details["d_plus_1_compact"] == "4/3/3"
    assert summary.primary_problem is None


# ---------------------------------------------------------------------------
# New details fields: date_issued, confidence, problems, wx
# ---------------------------------------------------------------------------

def _full_report() -> dict:
    """Minimal but realistic report covering all new parsed fields."""
    return {
        "dateIssued": "2026-03-05T00:00:00Z",
        "dangerRatings": [
            {
                "ratings": {
                    "alp": {"rating": {"value": "considerable"}},
                    "tln": {"rating": {"value": "considerable"}},
                    "btl": {"rating": {"value": "considerable"}},
                }
            }
        ],
        "confidence": {"rating": {"value": "moderate"}, "statements": ["Uncertain due to buried weak layers."]},
        "summaries": [
            {
                "type": {"value": "avalanche-summary"},
                "content": "<p>Size 3 avalanche on Jan 26 layer.</p>",
            },
            {
                "type": {"value": "snowpack-summary"},
                "content": "<p>Surface hoar buried 130-160cm.</p>",
            },
            {
                "type": {"value": "weather-summary"},
                "content": (
                    "<p>Intro text.</p>"
                    "<p><strong>Tonight</strong> Isolated Flurries. Alpine Low -6°C. "
                    "Freezing level (FZL) 1300m. Light West ridgetop wind.</p>"
                    "<p><strong>Thu</strong> Sunny periods. Alpine High -5°C. "
                    "FZL 1500m. Gusty moderate W winds.</p>"
                ),
            },
        ],
        "problems": [
            {
                "type": {"value": "persistentslab"},
                "comment": "<p>Two weak layers buried 100-130cm.</p>",
                "data": {
                    "elevations": [
                        {"value": "alp"},
                        {"value": "tln"},
                        {"value": "btl"},
                    ],
                    "aspects": [
                        {"value": "n"}, {"value": "ne"}, {"value": "e"}, {"value": "se"},
                        {"value": "s"}, {"value": "sw"}, {"value": "w"}, {"value": "nw"},
                    ],
                    "likelihood": {"value": "possible"},
                    "expectedSize": {"min": "1.5", "max": "4.0"},
                },
            },
            {
                "type": {"value": "stormslab"},
                "comment": "<p>Fresh storm slabs on open terrain.</p>",
                "data": {
                    "elevations": [{"value": "alp"}, {"value": "tln"}],
                    "aspects": [
                        {"value": "n"}, {"value": "ne"}, {"value": "e"}, {"value": "se"},
                        {"value": "s"}, {"value": "sw"}, {"value": "w"}, {"value": "nw"},
                    ],
                    "likelihood": {"value": "possible"},
                    "expectedSize": {"min": "1.0", "max": "2.5"},
                },
            },
        ],
        "terrainAndTravelAdvice": ["Avoid steep loaded terrain."],
    }


def test_normalize_date_issued():
    summary = normalize_avalanche_summary(_full_report())
    assert summary.details["date_issued"] == "03-05"


def test_normalize_confidence():
    summary = normalize_avalanche_summary(_full_report())
    assert summary.details["confidence"] == "Mod"


def test_normalize_problems_count():
    summary = normalize_avalanche_summary(_full_report())
    assert len(summary.details["problems"]) == 2


def test_normalize_problem_persistent_slab():
    summary = normalize_avalanche_summary(_full_report())
    ps = summary.details["problems"][0]
    assert ps["type"] == "PS"
    assert ps["elevations"] == "1-1-1"  # alp-tln-btl all present
    assert ps["aspects"] == "ALL"
    assert ps["likelihood"] == "Pos"
    assert ps["size"] == "1.5-4"


def test_normalize_problem_storm_slab_partial_elevation():
    summary = normalize_avalanche_summary(_full_report())
    ss = summary.details["problems"][1]
    assert ss["type"] == "SS"
    assert ss["elevations"] == "1-1-0"  # alp=1, tln=1, btl=0


def test_normalize_wx_two_sections():
    summary = normalize_avalanche_summary(_full_report())
    wx = summary.details["wx"]
    assert len(wx) == 2
    assert wx[0]["label"] == "Tnite"
    assert wx[1]["label"] == "Thu"


def test_normalize_wx_tonight_text_abbreviated():
    summary = normalize_avalanche_summary(_full_report())
    text = summary.details["wx"][0]["text"]
    assert "FZL1300" in text
    assert "-6C" in text
    assert "Lt" in text  # Light → Lt


def test_normalize_wx_tomorrow_text_abbreviated():
    summary = normalize_avalanche_summary(_full_report())
    text = summary.details["wx"][1]["text"]
    assert "FZL1500" in text
    assert "-5C" in text
    assert "GstMod" in text  # "Gusty moderate" → GstMod


# ---------------------------------------------------------------------------
# extract_claude_text_payload
# ---------------------------------------------------------------------------

def test_extract_claude_text_payload_includes_summaries():
    report = _full_report()
    payload = extract_claude_text_payload(report)
    assert "Size 3 avalanche" in payload
    assert "Surface hoar buried" in payload


def test_extract_claude_text_payload_excludes_weather_summary():
    report = _full_report()
    payload = extract_claude_text_payload(report)
    # Weather is in base message; should not be duplicated in Claude payload
    assert "FZL" not in payload
    assert "Isolated Flurries" not in payload


def test_extract_claude_text_payload_includes_confidence_statements():
    report = _full_report()
    payload = extract_claude_text_payload(report)
    assert "buried weak layers" in payload


def test_extract_claude_text_payload_includes_problem_comments():
    report = _full_report()
    payload = extract_claude_text_payload(report)
    assert "Two weak layers" in payload
    assert "storm slabs" in payload.lower()


def test_extract_claude_text_payload_strips_html():
    report = _full_report()
    payload = extract_claude_text_payload(report)
    assert "<p>" not in payload
    assert "</p>" not in payload
