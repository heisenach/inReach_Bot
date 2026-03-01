# inreach-bot

Automates Avalanche Canada forecast retrieval and sends compact messages to a Garmin MapShare endpoint.

## Key behavior

- Trip settings are user-provided through GitHub workflow inputs.
- `gst_utc_offset` is required each time (for example `UTC-07:00`).
- Coordinates are required as general config: `latitude`/`longitude`.
- `preview_only=true` is enforced first; preview artifacts are generated before live sends.
- Scheduled workflow runs every 30 minutes and only sends when gate checks pass.
- Current code path is avalanche-only (OpenSnow fetch is intentionally skipped).

## Required repository secret

Create at least one secret that contains OpenSnow auth JSON. Example value:

```json
{
  "base_url": "https://api.opensnow.com",
  "coordinates_path": "/v1/forecast/point",
  "point_path": "/v1/forecast/point/{point_id}",
  "headers": {
    "User-Agent": "inreach-bot/0.1"
  },
  "cookies": {
    "session": "..."
  }
}
```

Then pass the secret name in `opensnow_auth_secret_name` when running `Configure Trip`.

## Workflows

1. `Configure Trip`: writes `.trip_state/current_trip.json`.
2. `Preview Forecast Data`: fetches both sources and uploads raw + normalized artifacts.
3. `Activate Sending`: sets `preview_only=false`.
4. `Scheduled Send`: runs on cron and sends only when eligible.

## Local usage

```bash
python -m pip install -e .[dev]
export OPENSNOW_AUTH='{"base_url":"https://api.opensnow.com","headers":{},"cookies":{}}'
python -m inreach_bot.main --mode preview
python -m inreach_bot.main --mode send --skip-gate
pytest -q
```

## Notes

- MapShare forms can change over time; Playwright selector updates may be needed.
- If OpenSnow fetch fails, fallback weather (`open-meteo`) is used when coordinates are available.
- If Avalanche Canada fetch fails, sending is aborted and an alert issue is raised.
