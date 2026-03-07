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
        sender_contact="test@example.com",
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
    now = datetime(2026, 2, 28, 19, 0, tzinfo=UTC)  # UTC-07 => 12:00 local Feb 28, in dead zone
    decision = build_send_decision(cfg, now_utc=now)
    assert decision.eligible_now is False
    assert "tolerance" in decision.reason


def test_send_decision_catchup_after_midnight():
    cfg = base_config()
    # 02:00 local on Feb 28 = 09:00 UTC Feb 28; target was 20:00 local Feb 27
    now = datetime(2026, 2, 28, 9, 0, tzinfo=UTC)
    decision = build_send_decision(cfg, now_utc=now)
    assert decision.eligible_now is True
    assert decision.idempotency_key.startswith("2026-02-27::")  # key is for previous day


def test_send_decision_catchup_does_not_block_same_day_send(monkeypatch, tmp_path):
    from inreach_bot.config import persist_last_sent_key

    cfg = base_config()

    # Simulate: catch-up fired at 02:00 local Feb 28, stored key for Feb 27
    catchup_key = "2026-02-27::51.0000,-117.0000"
    last_sent_file = tmp_path / "last_sent.json"
    persist_last_sent_key(catchup_key, last_sent_file)
    monkeypatch.setattr("inreach_bot.config.LAST_SENT_PATH", last_sent_file)

    # Now it's 20:05 local Feb 28 — should still be eligible for Feb 28
    now = datetime(2026, 3, 1, 3, 5, tzinfo=UTC)  # UTC-07 => 20:05 local Feb 28
    decision = build_send_decision(cfg, now_utc=now)
    assert decision.eligible_now is True
    assert decision.idempotency_key.startswith("2026-02-28::")
