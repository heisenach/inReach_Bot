from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from .alerts.github_issue import post_or_update_alert
from .config import (
    ConfigError,
    build_send_decision,
    load_trip_config,
    persist_last_sent_key,
)
from .delivery.mapshare_playwright import deliver_messages_mapshare
from .formatters.message_builder import build_base_message
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        config = load_trip_config()
    except ConfigError as exc:
        _handle_error(f"Config error: {exc}")
        return 2

    try:
        avalanche_summary, avalanche_raw = fetch_avalanche_summary(config)
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

    report_payload = (
        avalanche_raw.get("point", {}).get("report", {})
        if isinstance(avalanche_raw, dict)
        else {}
    )
    if not isinstance(report_payload, dict):
        report_payload = {}

    # Total budget for Claude: up to 10 messages minus the base message and delimiter
    total_budget = 10 * config.message_max_chars - len(base_message) - len(" | ")
    if total_budget > 0 and report_payload:
        text_payload = extract_claude_text_payload(report_payload)
        if text_payload:
            try:
                claude_summary = summarize_report_with_claude(text_payload, total_budget)
            except ClaudeSummaryError as exc:
                claude_error = str(exc)
                _warn(f"Claude summary unavailable; using deterministic base only: {exc}", send_alert=True)

    artifacts_dir = Path(args.artifacts_dir)
    write_preview_artifacts(
        artifacts_dir,
        avalanche_raw=avalanche_raw,
        avalanche_summary=avalanche_summary,
        weather_summary=weather_summary,
        claude_summary=claude_summary,
        claude_error=claude_error,
    )

    outbound_message = f"{base_message} | {claude_summary}" if claude_summary else base_message

    if args.mode == "preview":
        print(f"\n{'='*60}")
        print(f"OUTBOUND MESSAGE ({len(outbound_message)} chars)")
        print("="*60)
        print(f"\n{outbound_message}")
        print(f"\n{'='*60}\n")
        _append_step_summary(
            "Preview complete",
            {
                "base_message": base_message,
                "weather_source": "skipped",
                "claude_used": str(bool(claude_summary)),
                "claude_error": claude_error or "",
                "preview_only": str(config.preview_only),
                "artifacts_dir": str(artifacts_dir.resolve()),
            },
        )
        return 0

    decision = build_send_decision(config)
    if not args.skip_gate and not decision.eligible_now:
        _append_step_summary("Send skipped", {"reason": decision.reason, "idempotency_key": decision.idempotency_key})
        return 0

    try:
        result = deliver_messages_mapshare(config.mapshare_url, [outbound_message], artifacts_dir / "delivery")
    except Exception as exc:
        _handle_error(f"MapShare delivery failed: {exc}")
        return 4

    persist_last_sent_key(decision.idempotency_key)
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
