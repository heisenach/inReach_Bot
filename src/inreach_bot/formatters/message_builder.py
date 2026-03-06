from __future__ import annotations

from ..types import AvalancheSummary


def build_base_message(avalanche: AvalancheSummary) -> str:
    """Build the deterministic base message: date, danger, confidence, problems, weather."""
    date_str = avalanche.details.get("date_issued", "")
    danger = format_d_plus_1_numeric(avalanche)
    conf = avalanche.details.get("confidence", "")
    problems: list[dict] = avalanche.details.get("problems", [])
    wx: list[dict] = avalanche.details.get("wx", [])

    base = f"{date_str} {danger} {conf}"
    for p in problems:
        base += f"|{p['type']}:{p['elevations']},{p['aspects']},{p['likelihood']},{p['size']}"
    for w in wx:
        base += f"|{w['label']}:{w['text']}"
    return base


def format_d_plus_1_numeric(avalanche: AvalancheSummary) -> str:
    alp = avalanche.danger_ratings_by_elevation.get("alp")
    tln = avalanche.danger_ratings_by_elevation.get("tln")
    btl = avalanche.danger_ratings_by_elevation.get("btl")
    if not (alp and tln and btl):
        raise ValueError("Missing required D+1 ratings for alp/tln/btl")
    return f"{alp}/{tln}/{btl}"


def choose_outbound_messages(
    base: str, claude: str, max_chars: int, max_messages: int | None = None
) -> list[str]:
    """Chunk base + claude into messages of max_chars each, breaking at word boundaries.

    Message 1: base + as much of claude as fits (joined with ' | ').
    Subsequent messages: remaining claude text, chunked to max_chars.
    If max_messages is None (default), no cap is applied.
    """
    if not claude:
        return [base[:max_chars]]

    delimiter = " | "
    combined = f"{base}{delimiter}{claude}"
    if len(combined) <= max_chars:
        return [combined]

    budget = max_chars - len(base) - len(delimiter)
    if budget > 0:
        chunk = _word_chunk(claude, budget)
        messages = [f"{base}{delimiter}{chunk}"]
        remainder = claude[len(chunk):].lstrip()
    else:
        messages = [base[:max_chars]]
        remainder = claude

    while remainder:
        if max_messages is not None and len(messages) >= max_messages:
            break
        chunk = _word_chunk(remainder, max_chars)
        messages.append(chunk)
        remainder = remainder[len(chunk):].lstrip()

    return messages


def _word_chunk(text: str, max_chars: int) -> str:
    """Return up to max_chars of text, breaking at the last word boundary."""
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)
    return text[:cut] if cut > 0 else text[:max_chars]


def claude_summary_budget(base_message: str, max_chars: int, delimiter: str = " | ") -> int:
    remaining = max_chars - len(base_message) - len(delimiter)
    return max(0, remaining)


def append_claude_summary(base_message: str, claude_summary: str, max_chars: int, delimiter: str = " | ") -> str:
    summary = claude_summary.strip()
    if not summary:
        return _truncate(base_message, max_chars)
    combined = f"{base_message}{delimiter}{summary}"
    return _truncate(combined, max_chars)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    suffix = " [truncated]"
    if max_chars <= len(suffix):
        return text[:max_chars]
    return text[: max_chars - len(suffix)] + suffix
