from __future__ import annotations

import re


def hook_matches(matcher: str | None, value: str | None) -> bool:
    text = (matcher or "").strip()
    if text in {"", "*"}:
        return True
    value = value or ""
    if _is_simple_alternatives(text):
        return value in {part for part in text.split("|") if part}
    try:
        return re.search(text, value) is not None
    except re.error:
        return False


def _is_simple_alternatives(text: str) -> bool:
    if "|" not in text:
        return bool(re.fullmatch(r"[A-Za-z0-9_.:/-]+", text))
    return bool(re.fullmatch(r"[A-Za-z0-9_.:/-]+(\|[A-Za-z0-9_.:/-]+)+", text))
