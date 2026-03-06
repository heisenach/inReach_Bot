from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)


class MapShareDeliveryError(RuntimeError):
    pass


def deliver_messages_mapshare(
    mapshare_url: str,
    messages: list[str],
    sender_contact: str,
    artifacts_dir: Path,
    timeout_ms: int = 30000,
) -> dict[str, int | str]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    attempts = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            for idx, message in enumerate(messages, 1):
                log.info("Sending message %d/%d (%d chars): %s", idx, len(messages), len(message), message)
                sent = False
                for _ in range(2):
                    attempts += 1
                    try:
                        log.info("  Attempt %d...", attempts)
                        _send_single_message(page, mapshare_url, sender_contact, message, timeout_ms)
                        sent = True
                        log.info("  Message %d/%d sent successfully", idx, len(messages))
                        break
                    except Exception as exc:
                        log.warning("  Attempt %d failed: %s", attempts, exc)
                        _capture_debug(page, artifacts_dir, attempts)
                if not sent:
                    raise MapShareDeliveryError(f"Unable to send message {idx}/{len(messages)} after retries")
        finally:
            browser.close()

    return {"message_count": len(messages), "attempts": attempts, "channel": "mapshare"}


def _send_single_message(page, url: str, sender_contact: str, message: str, timeout_ms: int) -> None:
    log.info("Navigating to %s", url)
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

    log.info("Waiting for Message button...")
    page.wait_for_selector("[data-test-id='topBtnMessage']", timeout=timeout_ms)
    log.info("Clicking Message button")
    page.locator("[data-test-id='topBtnMessage']").click(timeout=timeout_ms)

    log.info("Filling sender contact")
    page.get_by_role("textbox", name="Your Email or Mobile Phone:").fill(sender_contact, timeout=timeout_ms)

    log.info("Filling message text")
    textbox = page.get_by_role("textbox", name="Message")
    textbox.fill(message, timeout=timeout_ms)

    log.info("Clicking Send")
    page.locator("[data-test-id='MessageUserSend']").click(timeout=timeout_ms)

    # Wait briefly for any post-submit UI changes, then assume success.
    page.wait_for_timeout(2000)
    log.info("Send complete")


def _capture_debug(page, artifacts_dir: Path, attempt: int) -> None:
    page.screenshot(path=str(artifacts_dir / f"mapshare_attempt_{attempt}.png"), full_page=True)
    (artifacts_dir / f"mapshare_attempt_{attempt}.html").write_text(page.content(), encoding="utf-8")
