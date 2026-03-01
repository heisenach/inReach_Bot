from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..types import AvalancheSummary, WeatherSummary


def write_preview_artifacts(
    base_dir: Path,
    avalanche_raw: dict[str, Any],
    opensnow_raw: dict[str, Any],
    avalanche_summary: AvalancheSummary,
    weather_summary: WeatherSummary,
) -> dict[str, Path]:
    raw_dir = base_dir / "raw"
    normalized_dir = base_dir / "normalized"
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "avalanche_raw": raw_dir / "avalanche.json",
        "opensnow_raw": raw_dir / "opensnow.json",
        "weather_verbose": normalized_dir / "weather_verbose.json",
        "avalanche_verbose": normalized_dir / "avalanche_verbose.json",
    }

    paths["avalanche_raw"].write_text(json.dumps(avalanche_raw, indent=2), encoding="utf-8")
    paths["opensnow_raw"].write_text(json.dumps(opensnow_raw, indent=2), encoding="utf-8")
    paths["weather_verbose"].write_text(json.dumps(asdict(weather_summary), indent=2), encoding="utf-8")
    paths["avalanche_verbose"].write_text(json.dumps(asdict(avalanche_summary), indent=2), encoding="utf-8")

    return paths