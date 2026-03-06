from __future__ import annotations

from datetime import UTC, datetime

from inreach_bot.config import build_send_decision
from inreach_bot.types import TripConfig


def base_config(**overrides):
    cfg = TripConfig(
        start_date=datetime(2026, 2, 27, tzinfo=UTC).date(),
        end_date=datetime(2026, 3, 2, tzinfo=UTC).date(),
        send_time_gst="20:00",
        gst_utc_offset="UTC-07:00",
        latitude=51.0,
        longitude=-117.0,
        mapshare_url="https://example.com",
        preview_only=False,
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def test_send_decision_eligible_within_window(monkeypatch):
    cfg = base_config()
    now = datetime(2026, 2, 28, 3, 5, tzinfo=UTC)  # UTC-07 => 20:05 local previous date

    # local date is 2026-02-27 and time 20:05
    decision = build_send_decision(cfg, now_utc=now)
    assert decision.eligible_now is True


def test_send_decision_skips_preview_mode():
    cfg = base_config(preview_only=True)
    now = datetime(2026, 2, 28, 3, 0, tzinfo=UTC)
    decision = build_send_decision(cfg, now_utc=now)
    assert decision.eligible_now is False
    assert decision.reason == "preview_only=true"


def test_send_decision_outside_time_window():
    cfg = base_config()
    now = datetime(2026, 2, 28, 6, 0, tzinfo=UTC)  # UTC-07 => 23:00 local
    decision = build_send_decision(cfg, now_utc=now)
    assert decision.eligible_now is False
    assert "tolerance" in decision.reason
