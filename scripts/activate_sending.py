from __future__ import annotations

from inreach_bot.config import load_trip_config, to_json_dict, write_trip_config


def main() -> int:
    cfg = load_trip_config()
    payload = to_json_dict(cfg)
    payload["preview_only"] = False
    write_trip_config(payload)
    print("preview_only set to false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())