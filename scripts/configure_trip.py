from __future__ import annotations

import argparse

from inreach_bot.config import load_trip_config, to_json_dict, write_trip_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure trip state")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--send-time-gst", required=True)
    parser.add_argument("--gst-utc-offset", required=True)
    parser.add_argument("--latitude", required=True)
    parser.add_argument("--longitude", required=True)
    parser.add_argument("--mapshare-url", required=True)
    parser.add_argument("--sender-contact", required=True, help="Email or phone number shown as sender on MapShare")
    parser.add_argument("--preview-only", default="true", choices=["true", "false"])
    parser.add_argument("--message-max-chars", default="160")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    payload = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "send_time_gst": args.send_time_gst,
        "gst_utc_offset": args.gst_utc_offset,
        "latitude": args.latitude,
        "longitude": args.longitude,
        "mapshare_url": args.mapshare_url,
        "sender_contact": args.sender_contact,
        "preview_only": args.preview_only == "true",
        "message_max_chars": int(args.message_max_chars),
    }

    write_trip_config(payload)

    # Re-read with strict validation so invalid configs never get committed.
    cfg = load_trip_config()
    print(to_json_dict(cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
