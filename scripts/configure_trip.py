from __future__ import annotations

import argparse

from inreach_bot.config import load_trip_config, to_json_dict, write_trip_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure trip state")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--send-time-gst", required=True)
    parser.add_argument("--gst-utc-offset", required=True)
    parser.add_argument("--latitude", required=False)
    parser.add_argument("--longitude", required=False)
    parser.add_argument("--avcan-lat", required=False)  # backward compatible alias
    parser.add_argument("--avcan-lon", required=False)  # backward compatible alias
    parser.add_argument("--avcan-region-mode", required=False, default="region_name", choices=["area_id", "region_name"])
    parser.add_argument("--avcan-region-value", required=False, default="")
    parser.add_argument("--opensnow-target-mode", required=False, default="coordinates", choices=["coordinates", "point_id"])
    parser.add_argument("--opensnow-lat")
    parser.add_argument("--opensnow-lon")
    parser.add_argument("--opensnow-point-id")
    parser.add_argument("--mapshare-url", required=True)
    parser.add_argument("--opensnow-auth-secret-name", required=False, default="")
    parser.add_argument("--preview-only", default="true", choices=["true", "false"])
    parser.add_argument("--message-max-chars", default="480")
    parser.add_argument("--send-tolerance-minutes", default="20")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    latitude = args.latitude if args.latitude not in (None, "") else args.avcan_lat
    longitude = args.longitude if args.longitude not in (None, "") else args.avcan_lon

    payload = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "send_time_gst": args.send_time_gst,
        "gst_utc_offset": args.gst_utc_offset,
        "latitude": latitude,
        "longitude": longitude,
        "avcan_region_mode": args.avcan_region_mode,
        "avcan_region_value": args.avcan_region_value,
        "opensnow_target_mode": args.opensnow_target_mode,
        "opensnow_lat": args.opensnow_lat,
        "opensnow_lon": args.opensnow_lon,
        "opensnow_point_id": args.opensnow_point_id,
        "mapshare_url": args.mapshare_url,
        "opensnow_auth_secret_name": args.opensnow_auth_secret_name,
        "preview_only": args.preview_only == "true",
        "message_max_chars": int(args.message_max_chars),
        "send_tolerance_minutes": int(args.send_tolerance_minutes),
    }

    write_trip_config(payload)

    # Re-read with strict validation so invalid configs never get committed.
    cfg = load_trip_config()
    print(to_json_dict(cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
