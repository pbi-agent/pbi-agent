"""Conservative old/new text replacement helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import re


TRAILING_WHITESPACE_REPLACE_WARNING = (
    "used fuzzy old_string match ignoring trailing whitespace"
)
TRIMMED_WHITESPACE_REPLACE_WARNING = (
    "used fuzzy old_string match ignoring leading/trailing whitespace"
)
UNICODE_NORMALIZED_REPLACE_WARNING = (
    "used fuzzy old_string match after normalizing Unicode punctuation/spaces"
)


@dataclass(frozen=True, slots=True)
class TextReplacementResult:
    content: str
    replacements: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchStrategy:
    normalize: Callable[[str], str]
    warning: str | None = None
    substring: bool = False


def replace_text(
    content: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
) -> TextReplacementResult:
    if old_string == "":
        raise ValueError("'old_string' must be non-empty.")
    if old_string == new_string:
        raise ValueError("'old_string' and 'new_string' must be different.")

    normalized_content = _normalize_text_newlines(content)
    normalized_old = _normalize_text_newlines(old_string)
    normalized_new = _normalize_text_newlines(new_string)

    for strategy in _strategies():
        matches = _find_matches(normalized_content, normalized_old, strategy)
        if not matches:
            continue
        if not replace_all and len(matches) > 1:
            raise ValueError(
                "old_string matched multiple locations; include more surrounding "
                "context or set replace_all=true."
            )
        new_content = _apply_replacements(normalized_content, matches, normalized_new)
        warnings = (strategy.warning,) if strategy.warning is not None else ()
        return TextReplacementResult(
            content=_restore_newline_style(new_content, content),
            replacements=len(matches),
            warnings=warnings,
        )

    raise ValueError(
        "old_string was not found in the file. Re-read the file and provide "
        "an exact block with enough surrounding context."
    )


def _strategies() -> tuple[MatchStrategy, ...]:
    return (
        MatchStrategy(lambda value: value, substring=True),
        MatchStrategy(str.rstrip, TRAILING_WHITESPACE_REPLACE_WARNING),
        MatchStrategy(str.strip, TRIMMED_WHITESPACE_REPLACE_WARNING),
        MatchStrategy(_normalize_common_unicode, UNICODE_NORMALIZED_REPLACE_WARNING),
    )


def _find_matches(
    content: str,
    pattern: str,
    strategy: MatchStrategy,
) -> list[tuple[int, int]]:
    if strategy.substring:
        return _find_substring_matches(content, pattern)
    content_lines = content.split("\n")
    pattern_lines = pattern.split("\n")
    if len(pattern_lines) == 1:
        return _find_single_line_matches(content_lines, pattern, strategy.normalize)
    return _find_multiline_matches(content_lines, pattern_lines, strategy.normalize)


def _find_substring_matches(content: str, pattern: str) -> list[tuple[int, int]]:
    if "\n" not in pattern and _is_probable_full_line(content, pattern):
        return []
    matches: list[tuple[int, int]] = []
    start = 0
    while True:
        index = content.find(pattern, start)
        if index == -1:
            return matches
        matches.append((index, index + len(pattern)))
        start = index + 1


def _is_probable_full_line(content: str, pattern: str) -> bool:
    if pattern.startswith((" ", "\t")) or pattern.endswith((" ", "\t")):
        return False
    for line in content.split("\n"):
        if line.startswith(pattern) and line[len(pattern) :].strip() == "":
            return True
        if line.endswith(pattern) and line[: -len(pattern)].strip() == "":
            return True
        if pattern in line and re.fullmatch(r"\s*" + re.escape(pattern) + r"\s*", line):
            return True
    return False


def _find_single_line_matches(
    content_lines: list[str],
    pattern: str,
    normalize: Callable[[str], str],
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    offsets = _line_offsets(content_lines)
    normalized_pattern = normalize(pattern)

    for index, line in enumerate(content_lines):
        if normalize(line) != normalized_pattern:
            continue
        matches.append((offsets[index], offsets[index] + len(line)))
    return matches


def _find_multiline_matches(
    content_lines: list[str],
    pattern_lines: list[str],
    normalize: Callable[[str], str],
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    offsets = _line_offsets(content_lines)
    pattern_length = len(pattern_lines)
    normalized_pattern = [normalize(line) for line in pattern_lines]

    for start in range(0, len(content_lines) - pattern_length + 1):
        candidate = content_lines[start : start + pattern_length]
        if [normalize(line) for line in candidate] != normalized_pattern:
            continue
        end_line = start + pattern_length - 1
        matches.append(
            (offsets[start], offsets[end_line] + len(content_lines[end_line]))
        )
    return matches


def _line_offsets(lines: list[str]) -> list[int]:
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1
    return offsets


def _apply_replacements(
    content: str,
    matches: list[tuple[int, int]],
    new_string: str,
) -> str:
    result = content
    for start, end in sorted(matches, key=lambda item: item[0], reverse=True):
        result = result[:start] + new_string + result[end:]
    return result


_UNICODE_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2026": "...",
        "\u00a0": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u205f": " ",
        "\u3000": " ",
    }
)


def _normalize_common_unicode(value: str) -> str:
    return value.strip().translate(_UNICODE_TRANSLATION)


def _normalize_text_newlines(text: str) -> str:
    return text.replace("\r\n", "\n")


def _restore_newline_style(text: str, original: str) -> str:
    if "\r\n" not in original:
        return text
    return text.replace("\n", "\r\n")
