from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", required=True)
    parser.add_argument("--path", default=".trip_state/current_trip.json")
    args = parser.parse_args()

    data = json.loads(Path(args.path).read_text(encoding="utf-8"))
    value = data.get(args.field, "")
    print(value if value is not None else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())