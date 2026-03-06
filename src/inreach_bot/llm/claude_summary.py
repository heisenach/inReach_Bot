from __future__ import annotations

import os
import re

import anthropic

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are a backcountry avalanche safety assistant. "
    "The danger rating, date, confidence level, avalanche problems, and weather outlook "
    "are already included in the base inReach message. "
    "Your task: summarize the instability narrative, snowpack story, and any notable confidence caveats "
    "from the provided forecast text. You have a generous character budget — use it to convey thorough, "
    "safety-critical detail. "
    "Output plain text only, no headers, no bullets, no emojis, no HTML. "
    "Prioritize safety-critical instability signals and human-triggering risk."
)


class ClaudeSummaryError(RuntimeError):
    pass


def summarize_report_with_claude(text_payload: str, max_chars: int) -> str:
    """Summarize forecast text for the Claude portion of the inReach message.

    Args:
        text_payload: Plain-text blob of descriptive forecast content (HTML already stripped).
        max_chars: Maximum character budget for the returned summary.
    """
    if max_chars <= 0:
        return ""

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ClaudeSummaryError("ANTHROPIC_API_KEY is missing")

    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    user_prompt = (
        f"Summarize the following avalanche forecast text for a Garmin inReach satellite message.\n"
        f"CHARACTER BUDGET: exactly {max_chars} characters. Your entire response must be {max_chars} characters or fewer.\n"
        "End on a complete sentence. Write in continuous plain text only. No headers, no bullets, no emojis, no markdown.\n"
        "Prioritize safety-critical information first (instability signals, human-triggering risk, weak layers).\n\n"
        f"{text_payload}"
    )

    # Allow enough tokens for the full budget (~0.75 chars/token for English prose), capped at 4096
    max_tokens = min(4096, max(300, int(max_chars / 0.75)))

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:
        raise ClaudeSummaryError(f"Claude API call failed: {exc}") from exc

    try:
        raw_text = message.content[0].text
    except Exception as exc:
        raise ClaudeSummaryError("Claude response did not contain text content") from exc

    return _normalize_text(raw_text)


def _normalize_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
