from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..types import AvalancheSummary, WeatherSummary


def write_preview_artifacts(
    base_dir: Path,
    avalanche_raw: dict[str, Any],
    avalanche_summary: AvalancheSummary,
    weather_summary: WeatherSummary,
    claude_summary: str | None = None,
    claude_error: str | None = None,
) -> dict[str, Path]:
    raw_dir = base_dir / "raw"
    normalized_dir = base_dir / "normalized"
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "avalanche_raw": raw_dir / "avalanche.json",
        "weather_verbose": normalized_dir / "weather_verbose.json",
        "avalanche_verbose": normalized_dir / "avalanche_verbose.json",
        "claude_summary": normalized_dir / "claude_summary.txt",
        "claude_status": normalized_dir / "claude_status.json",
    }

    paths["avalanche_raw"].write_text(json.dumps(avalanche_raw, indent=2), encoding="utf-8")
    paths["weather_verbose"].write_text(json.dumps(asdict(weather_summary), indent=2), encoding="utf-8")
    paths["avalanche_verbose"].write_text(json.dumps(asdict(avalanche_summary), indent=2), encoding="utf-8")
    paths["claude_summary"].write_text((claude_summary or "").strip(), encoding="utf-8")
    paths["claude_status"].write_text(
        json.dumps(
            {
                "used": bool(claude_summary),
                "error": claude_error,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return paths
