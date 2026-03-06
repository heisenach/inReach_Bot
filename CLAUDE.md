# CLAUDE.md — inreach-bot

Guidance for Claude Code when working in this repository.

## Project overview

**inreach-bot** fetches Avalanche Canada forecasts and delivers compact safety messages to a Garmin inReach device via MapShare browser automation. It runs on GitHub Actions cron, is configurable via workflow inputs, and uses Claude AI to optionally enrich messages.

Forecast source: **Avalanche Canada API** (lat/lon point lookup).

## Repository layout

```
src/inreach_bot/
├── main.py                    # CLI entry point (--mode preview|send, --skip-gate)
├── config.py                  # TripConfig loading + send gate logic
├── types.py                   # Dataclasses: TripConfig, AvalancheSummary, WeatherSummary, SendDecision
├── providers/
│   ├── avcan.py               # Avalanche Canada API (primary data source)
│   └── weather_fallback.py    # Open-Meteo fallback (unused in default path)
├── formatters/
│   ├── message_builder.py     # D+1 "A/T/B" formatting, Claude summary appending
│   └── verbose_dump.py        # Preview artifact serialization
├── delivery/
│   └── mapshare_playwright.py # Playwright headless browser → MapShare form
├── alerts/
│   └── github_issue.py        # GitHub issue creation/commenting on failures
└── llm/
    └── claude_summary.py      # Anthropic API wrapper with graceful fallback

scripts/                       # Called by GitHub Actions workflows
.trip_state/                   # Runtime state (current_trip.json, last_sent.json)
.github/workflows/             # Four workflows: configure-trip, preview, activate-sending, scheduled-send
tests/                         # pytest suite with fixtures/
```

## Development setup

```bash
python -m pip install -e .[dev]
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-haiku-4-5-20251001"   # optional
python -m inreach_bot.main --mode preview
python -m inreach_bot.main --mode send --skip-gate
pytest -q
```

Python >= 3.11 is required. Use `from __future__ import annotations` and `datetime.UTC` conventions already established in the codebase.

## Key environment variables

| Variable | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (for summaries) | Never commit |
| `ANTHROPIC_MODEL` | No | Defaults to `claude-haiku-4-5-20251001` |
| `GITHUB_TOKEN` | No | Auto-set in Actions; for issue alerts |
| `GITHUB_REPOSITORY` | No | Auto-set in Actions |
| `GITHUB_STEP_SUMMARY` | No | Auto-set in Actions |

Do not store secrets in code or tracked files. `.env.example` exists for local dev reference only.

## Core data flow

1. Load `TripConfig` from `.trip_state/current_trip.json`
2. Fetch `AvalancheSummary` from Avalanche Canada API — abort with exit 3 if this fails
3. Build base deterministic message via `build_avalanche_only_message()` → `"4/3/3"` (Alp/Tln/Btl D+1 numeric)
4. Attempt Claude summary within remaining char budget; fall back silently on any failure
5. Gate checks via `build_send_decision()` (date range, time window, idempotency)
6. Deliver combined message via Playwright → MapShare; abort with exit 4 on failure
7. Persist idempotency key to `.trip_state/last_sent.json`

## Send gate logic (config.py)

`build_send_decision()` returns `eligible_now=False` when:
- `preview_only=true` in trip state
- Local date is outside `[start_date, end_date]`
- Local time is outside `send_time_gst ± send_tolerance_minutes`
- Idempotency key already exists for today's local date

Timezone is handled via `gst_utc_offset` (`UTC±HH:MM` format). All comparisons are done in local trip time.

## Message formatting conventions

- Base message: bare `"A/T/B"` numeric string, e.g. `"4/3/3"` (Alp/Tln/Btl)
- Danger ratings: 1=Low, 2=Moderate, 3=Considerable, 4=High, 5=Extreme
- Claude summary appended as `"<base> | <summary>"` up to `max_chars` limit
- `max_chars` from `TripConfig`; budget calculated by `claude_summary_budget()`
- Messages exceeding limit are truncated with `"[truncated]"` suffix
- **No headers, no bullets, no emojis** in outbound messages (inReach constraint)

## Avalanche Canada parser (providers/avcan.py)

The API JSON schema varies; the parser tolerates this via:
- Multiple candidate key paths for danger ratings
- Elevation key normalization (`alp`/`alpine`/`upper`, `tln`/`treeline`/`treeLine`, `btl`/`belowtreeline`/etc.)
- Rating normalization: numeric (1–5) or text (`low`→1, `moderate`→2, `considerable`→3, `high`→4, `extreme`→5)

Do not simplify this tolerance — schema drift is an expected production concern.

## Playwright / MapShare delivery (delivery/mapshare_playwright.py)

- Runs Chromium headless; up to 2 retry attempts per message
- Finds textarea/input, fills text, clicks send via regex match (`send|post|message|share`)
- Confirms delivery by waiting for `sent|success|delivered` text or input clear
- On failure: saves screenshots and HTML to `delivery/` subdir for debugging
- Selector logic may need updates if MapShare changes its form structure

## Error handling conventions

| Failure | Behaviour |
|---|---|
| `ConfigError` | Exit 2 |
| Avalanche Canada fetch fails | Exit 3, post GitHub issue |
| MapShare delivery fails | Exit 4, post GitHub issue |
| Claude summary fails | Log warning, fall back to D+1 message only, post issue |
| No GitHub context | `github_issue.py` silently no-ops |

## Testing

```bash
pytest -q                  # run all tests
pytest tests/test_avcan_provider.py -v   # single file
```

- Tests use `pytest` with `monkeypatch` for env vars and `tmp_path` for filesystem
- Fixtures live in `tests/fixtures/` (JSON samples for API responses)
- Do not mock `requests` at the module level — monkeypatch `requests.get` per test
- New providers or formatters need corresponding test files

## GitHub Actions workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `configure-trip.yml` | Manual | Write `.trip_state/current_trip.json`; sets `preview_only=true` |
| `preview.yml` | Manual | Run `--mode preview`; upload `artifacts/` |
| `activate-sending.yml` | Manual | Set `preview_only=false` |
| `scheduled-send.yml` | Cron (*/30 * * * *) + Manual | Gate-checked send; commits `last_sent.json` |

The scheduled workflow installs Playwright chromium. Do not remove that install step.

## Style conventions

- Dataclasses with `slots=True` for data transfer objects
- `_require(d, key)` pattern for strict config field extraction
- Providers return typed dataclasses, not raw dicts
- Claude summary errors use a dedicated `ClaudeSummaryError` exception class
- Keep the LLM system prompt safety-focused; do not broaden its scope

## Things to watch out for

- **`assert 0` in `main.py`**: may indicate in-progress debug state — check before running
- **MapShare selectors**: brittle by nature; regex-based fallback exists but may need tuning
- **Message character budget**: inReach messages have a hard limit; always run through `choose_outbound_messages()` before delivery
