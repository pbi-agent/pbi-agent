from __future__ import annotations

MAX_OUTPUT_CHARS = 1_000


def bound_output(text: str, *, limit: int = MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    """Bound text output while preserving both the beginning and the end."""
    if len(text) <= limit:
        return text, False

    if limit <= 0:
        return "", True

    omitted_chars = len(text) - limit

    while True:
        marker = f"\n... {omitted_chars} chars omitted ...\n"
        available = limit - len(marker)
        if available <= 0:
            if limit == 1:
                return "…", True
            return f"{text[: limit - 1]}…", True

        head = available // 2 + available % 2
        tail = available // 2
        new_omitted_chars = len(text) - head - tail
        if new_omitted_chars == omitted_chars:
            suffix = text[-tail:] if tail else ""
            return f"{text[:head]}{marker}{suffix}", True
        omitted_chars = new_omitted_chars
