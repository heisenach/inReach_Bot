"""Run this to visually debug the MapShare send flow."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# ── edit these ────────────────────────────────────────────────────────────────
MAPSHARE_URL = "https://share.garmin.com/SVO87"  # your MapShare URL
SENDER_CONTACT = "helen@eisenach.org"                # email or phone
MESSAGE = "DEBUG TEST - please ignore"
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=800)
        page = browser.new_page()

        print("→ Navigating to MapShare page...")
        page.goto(MAPSHARE_URL, wait_until="domcontentloaded")

        print("→ Waiting for Message button...")
        try:
            page.wait_for_selector("[data-test-id='topBtnMessage']", timeout=15000)
            print("  ✓ Found [data-test-id='topBtnMessage']")
        except Exception as e:
            print(f"  ✗ Not found: {e}")
            # try old td
            try:
                page.wait_for_selector("#topBtnMessage", timeout=5000)
                print("  ✓ Found #topBtnMessage (old td)")
            except Exception as e2:
                print(f"  ✗ Old td not found either: {e2}")

        print("→ Clicking Message button...")
        try:
            page.locator("[data-test-id='topBtnMessage']").click(timeout=10000)
            print("  ✓ Clicked")
        except Exception as e:
            print(f"  ✗ Click failed: {e}")
            input("  Browser paused — inspect manually. Press Enter to quit.")
            sys.exit(1)

        print("→ Waiting for dialog (textarea)...")
        try:
            page.wait_for_selector("textarea", timeout=15000)
            print("  ✓ Textarea appeared")
        except Exception as e:
            print(f"  ✗ Textarea did not appear: {e}")
            input("  Browser paused — inspect manually. Press Enter to quit.")
            sys.exit(1)

        print("→ Filling sender contact...")
        try:
            page.get_by_role("textbox", name="Your Email or Mobile Phone:").fill(SENDER_CONTACT)
            print("  ✓ Filled")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            input("  Browser paused — inspect manually. Press Enter to quit.")
            sys.exit(1)

        print("→ Filling message...")
        try:
            page.get_by_role("textbox", name="Message").fill(MESSAGE)
            print("  ✓ Filled")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            input("  Browser paused — inspect manually. Press Enter to quit.")
            sys.exit(1)

        print("→ Looking for Send button...")
        try:
            send_btn = page.locator("[data-test-id='MessageUserSend']")
            print(f"  Count: {send_btn.count()}")
            # DON'T click — just confirm we can find it
        except Exception as e:
            print(f"  ✗ Failed: {e}")

        input("\nDone. Inspect the browser, then press Enter to close.")
        browser.close()

if __name__ == "__main__":
    main()
