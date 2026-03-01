from __future__ import annotations

from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


class MapShareDeliveryError(RuntimeError):
    pass


def deliver_messages_mapshare(
    mapshare_url: str,
    messages: list[str],
    artifacts_dir: Path,
    timeout_ms: int = 25000,
) -> dict[str, int | str]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    attempts = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            for message in messages:
                sent = False
                for _ in range(2):
                    attempts += 1
                    try:
                        _send_single_message(page, mapshare_url, message, timeout_ms)
                        sent = True
                        break
                    except Exception:
                        _capture_debug(page, artifacts_dir, attempts)
                if not sent:
                    raise MapShareDeliveryError("Unable to send message via MapShare after retries")
        finally:
            browser.close()

    return {"message_count": len(messages), "attempts": attempts, "channel": "mapshare"}


def _send_single_message(page, url: str, message: str, timeout_ms: int) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

    textbox = page.locator("textarea").first
    if textbox.count() == 0:
        textbox = page.locator("input[type='text'], [contenteditable='true']").first
    if textbox.count() == 0:
        raise MapShareDeliveryError("Could not find message input field on MapShare page")

    textbox.click(timeout=timeout_ms)
    textbox.fill(message, timeout=timeout_ms)

    # Broad selector to survive minor UI changes.
    button = page.get_by_role("button", name=r"(?i)(send|post|message|share)").first
    if button.count() == 0:
        button = page.locator("button[type='submit'], input[type='submit']").first
    if button.count() == 0:
        raise MapShareDeliveryError("Could not find submit button on MapShare page")

    button.click(timeout=timeout_ms)

    try:
        page.wait_for_timeout(1500)
        if page.get_by_text(r"(?i)(sent|success|delivered)").count() == 0:
            # Some pages do not show explicit text. If input clears, treat as success.
            value = textbox.input_value(timeout=1000) if textbox.evaluate("el => 'value' in el") else ""
            if value.strip() == message.strip():
                raise MapShareDeliveryError("No send confirmation detected after submit")
    except PlaywrightTimeoutError as exc:
        raise MapShareDeliveryError("Timed out waiting for MapShare submit result") from exc


def _capture_debug(page, artifacts_dir: Path, attempt: int) -> None:
    page.screenshot(path=str(artifacts_dir / f"mapshare_attempt_{attempt}.png"), full_page=True)
    (artifacts_dir / f"mapshare_attempt_{attempt}.html").write_text(page.content(), encoding="utf-8")