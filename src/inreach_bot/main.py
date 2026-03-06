from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from .alerts.github_issue import post_or_update_alert
from .config import (
    ConfigError,
    build_send_decision,
    load_trip_config,
    persist_last_sent_key,
)
from .delivery.mapshare_playwright import deliver_messages_mapshare
from .formatters.message_builder import build_base_message, choose_outbound_messages
from .formatters.verbose_dump import write_preview_artifacts
from .llm.claude_summary import ClaudeSummaryError, summarize_report_with_claude
from .providers.avcan import extract_claude_text_payload, fetch_avalanche_summary
from .types import WeatherSummary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="inReach backcountry forecast bot")
    parser.add_argument("--mode", choices=["preview", "send"], required=True)
    parser.add_argument("--artifacts-dir", default="artifacts")
    parser.add_argument("--skip-gate", action="store_true", help="Run send without schedule gate checks")
    return parser.parse_args(argv)


log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    log.info("Mode: %s | skip-gate: %s", args.mode, args.skip_gate)

    log.info("Loading trip config...")
    try:
        config = load_trip_config()
        log.info("Config loaded: lat=%s lon=%s mapshare=%s", config.latitude, config.longitude, config.mapshare_url)
    except ConfigError as exc:
        _handle_error(f"Config error: {exc}")
        return 2

    log.info("Fetching avalanche forecast...")
    try:
        avalanche_summary, avalanche_raw = fetch_avalanche_summary(config)
        log.info("Avalanche fetch OK: status=%s", avalanche_summary.source_status)
    except Exception as exc:
        _handle_error(f"Avalanche fetch failed: {exc}")
        return 3

    weather_summary = WeatherSummary(
        source="avcan",
        source_status="ok",
        fetch_timestamp=avalanche_summary.fetch_timestamp,
        headline="Weather from AvCan forecast",
    )

    claude_summary = ""
    claude_error = None

    base_message = build_base_message(avalanche_summary)
    log.info("Base message (%d chars): %s", len(base_message), base_message)

    report_payload = (
        avalanche_raw.get("point", {}).get("report", {})
        if isinstance(avalanche_raw, dict)
        else {}
    )
    if not isinstance(report_payload, dict):
        report_payload = {}

    total_budget = 10 * config.message_max_chars - len(base_message) - len(" | ")
    log.info("Claude budget: %d chars | report_payload present: %s", total_budget, bool(report_payload))
    if total_budget > 0 and report_payload:
        text_payload = extract_claude_text_payload(report_payload)
        log.info("Claude text payload length: %d chars", len(text_payload) if text_payload else 0)
        if text_payload:
            log.info("Calling Claude for summary...")
            try:
                claude_summary = summarize_report_with_claude(text_payload, total_budget)
                log.info("Claude summary (%d chars): %s", len(claude_summary), claude_summary[:80])
            except ClaudeSummaryError as exc:
                claude_error = str(exc)
                log.warning("Claude summary failed: %s", exc)
                _warn(f"Claude summary unavailable; using deterministic base only: {exc}", send_alert=True)
        else:
            log.warning("No Claude text payload extracted from report")
    else:
        log.warning("Skipping Claude: budget=%d report_payload=%s", total_budget, bool(report_payload))

    artifacts_dir = Path(args.artifacts_dir)
    write_preview_artifacts(
        artifacts_dir,
        avalanche_raw=avalanche_raw,
        avalanche_summary=avalanche_summary,
        weather_summary=weather_summary,
        claude_summary=claude_summary,
        claude_error=claude_error,
    )

    outbound_messages = choose_outbound_messages(base_message, claude_summary, config.message_max_chars)
    log.info("%d outbound message(s)", len(outbound_messages))
    for i, msg in enumerate(outbound_messages, 1):
        log.info("  [%d/%d] (%d chars): %s", i, len(outbound_messages), len(msg), msg)

    if args.mode == "preview":
        print(f"\n{'='*60}")
        print(f"OUTBOUND MESSAGES ({len(outbound_messages)} total)")
        print("="*60)
        for i, msg in enumerate(outbound_messages, 1):
            print(f"\n[{i}/{len(outbound_messages)}] ({len(msg)} chars):\n{msg}")
        print(f"\n{'='*60}\n")
        _append_step_summary(
            "Preview complete",
            {
                "base_message": base_message,
                "message_count": str(len(outbound_messages)),
                "claude_used": str(bool(claude_summary)),
                "claude_error": claude_error or "",
                "preview_only": str(config.preview_only),
                "artifacts_dir": str(artifacts_dir.resolve()),
            },
        )
        return 0

    decision = build_send_decision(config)
    log.info("Send gate: eligible=%s reason=%s", decision.eligible_now, decision.reason)
    if not args.skip_gate and not decision.eligible_now:
        _append_step_summary("Send skipped", {"reason": decision.reason, "idempotency_key": decision.idempotency_key})
        return 0

    log.info("Delivering %d message(s) via MapShare...", len(outbound_messages))
    try:
        result = deliver_messages_mapshare(config.mapshare_url, outbound_messages, config.sender_contact, artifacts_dir / "delivery")
        log.info("Delivery result: %s", result)
    except Exception as exc:
        _handle_error(f"MapShare delivery failed: {exc}")
        return 4

    persist_last_sent_key(decision.idempotency_key)
    log.info("Idempotency key persisted: %s", decision.idempotency_key)
    _append_step_summary(
        "Send complete",
        {
            "reason": decision.reason,
            "idempotency_key": decision.idempotency_key,
            "message_count": str(result.get("message_count", "")),
            "attempts": str(result.get("attempts", "")),
        },
    )
    print(json.dumps({"status": "ok", "result": result, "decision": asdict(decision)}, indent=2))
    return 0


def _append_step_summary(title: str, kv: dict[str, str]) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    summary_file = Path(summary_path)
    lines = [f"## {title}\n"] + [f"- {k}: {v}\n" for k, v in kv.items()]
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with summary_file.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)


def _handle_error(message: str) -> None:
    print(message, file=sys.stderr)
    try:
        post_or_update_alert(message)
    except Exception:
        pass


def _warn(message: str, send_alert: bool = False) -> None:
    print(message, file=sys.stderr)
    if not send_alert:
        return
    try:
        post_or_update_alert(message)
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
