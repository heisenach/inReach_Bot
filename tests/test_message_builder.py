from __future__ import annotations

import pytest

from inreach_bot.formatters.message_builder import (
    append_claude_summary,
    build_base_message,
    choose_outbound_messages,
    claude_summary_budget,
    format_d_plus_1_numeric,
)
from inreach_bot.types import AvalancheSummary


def sample_avalanche(details: dict | None = None) -> AvalancheSummary:
    return AvalancheSummary(
        source_status="ok",
        fetch_timestamp="2026-02-28T00:00:00Z",
        danger_ratings_by_elevation={"alp": "4", "tln": "3", "btl": "3"},
        primary_problem=None,
        secondary_problem=None,
        travel_advice=None,
        valid_from="2026-02-28",
        valid_to="2026-03-01",
        source_url="https://avalanche.ca",
        details=details or {},
    )


def sample_avalanche_full() -> AvalancheSummary:
    return sample_avalanche(
        details={
            "date_issued": "03-05",
            "confidence": "Mod",
            "problems": [
                {"type": "PS", "elevations": "1-1-1", "aspects": "ALL", "likelihood": "Pos", "size": "1.5-4"},
                {"type": "SS", "elevations": "1-1-0", "aspects": "ALL", "likelihood": "Pos", "size": "1-2.5"},
            ],
            "wx": [
                {"label": "Tnite", "text": "Flurries -6C FZL1300 Lt W"},
                {"label": "Thu", "text": "Sunny -5C FZL1500 Mod W Gst"},
            ],
        }
    )


# ---------------------------------------------------------------------------
# format_d_plus_1_numeric
# ---------------------------------------------------------------------------

def test_format_d_plus_1_numeric():
    msg = format_d_plus_1_numeric(sample_avalanche())
    assert msg == "4/3/3"


def test_format_d_plus_1_numeric_requires_all_bands():
    avalanche = sample_avalanche()
    avalanche.danger_ratings_by_elevation.pop("btl")
    with pytest.raises(ValueError, match="alp/tln/btl"):
        format_d_plus_1_numeric(avalanche)


# ---------------------------------------------------------------------------
# build_base_message
# ---------------------------------------------------------------------------

def test_build_base_message_full():
    msg = build_base_message(sample_avalanche_full())
    assert msg.startswith("03-05 4/3/3 Mod")
    assert "|PS:1-1-1,ALL,Pos,1.5-4" in msg
    assert "|SS:1-1-0,ALL,Pos,1-2.5" in msg
    assert "|Tnite:Flurries -6C FZL1300 Lt W" in msg
    assert "|Thu:Sunny -5C FZL1500 Mod W Gst" in msg


def test_build_base_message_no_details():
    msg = build_base_message(sample_avalanche())
    # No extra segments when details are empty
    assert msg == " 4/3/3 "


# ---------------------------------------------------------------------------
# choose_outbound_messages
# ---------------------------------------------------------------------------

def test_choose_outbound_single_message_when_fits():
    base = "03-05 4/3/3 Mod"
    claude = "Avoid steep slopes."
    out = choose_outbound_messages(base, claude, max_chars=200)
    assert len(out) == 1
    assert out[0] == f"{base} | {claude}"


def test_choose_outbound_splits_when_over_limit():
    base = "03-05 4/3/3 Mod"
    claude = "x" * 200
    out = choose_outbound_messages(base, claude, max_chars=160)
    assert len(out) == 2
    assert all(len(m) <= 160 for m in out)
    assert out[0].startswith(base)


def test_choose_outbound_no_claude():
    base = "03-05 4/3/3 Mod"
    out = choose_outbound_messages(base, "", max_chars=160)
    assert len(out) == 1
    assert out[0] == base


def test_choose_outbound_base_only_when_no_budget():
    base = "x" * 158  # leaves no room for " | " + claude
    claude = "important safety info"
    out = choose_outbound_messages(base, claude, max_chars=160)
    # msg1 is base (no budget for claude inline), msg2 is claude remainder
    assert len(out[0]) <= 160
    assert len(out) >= 2


def test_choose_outbound_max_five_messages():
    base = "03-05 3/3/3 Mod"
    claude = "x" * (4 * 160 + 50)  # would need 5+ messages
    out = choose_outbound_messages(base, claude, max_chars=160, max_messages=5)
    assert len(out) <= 5
    assert all(len(m) <= 160 for m in out)


# ---------------------------------------------------------------------------
# claude_summary_budget / append_claude_summary (legacy helpers, keep working)
# ---------------------------------------------------------------------------

def test_claude_summary_budget():
    base = "4/3/3"
    budget = claude_summary_budget(base, max_chars=60)
    assert budget == 60 - len(base) - len(" | ")


def test_append_claude_summary_within_budget():
    base = "4/3/3"
    out = append_claude_summary(base, "Avoid steep loaded slopes.", max_chars=80)
    assert out.startswith(base + " | ")
    assert len(out) <= 80


def test_append_claude_summary_fallback_to_base_when_empty():
    base = "4/3/3"
    out = append_claude_summary(base, "", max_chars=80)
    assert out == base
