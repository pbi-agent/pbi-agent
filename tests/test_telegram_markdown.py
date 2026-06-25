from __future__ import annotations

from pbi_agent.channels.telegram_markdown import (
    format_telegram_markdown_chunks,
    markdown_to_telegram_entities,
    split_telegram_text,
)


def test_split_telegram_text_counts_utf16_units() -> None:
    chunks = split_telegram_text("a" * 4095 + "🙂")

    assert chunks == ["a" * 4095, "🙂"]


def test_markdown_to_telegram_entities_uses_utf16_offsets() -> None:
    text, entities = markdown_to_telegram_entities(
        "# Title\n🙂 **bold** and `code` plus [link](https://example.com)\n"
    )

    assert text == "Title\n🙂 bold and code plus link\n"
    assert entities == [
        {"type": "bold", "offset": 0, "length": 5},
        {"type": "bold", "offset": 9, "length": 4},
        {"type": "code", "offset": 18, "length": 4},
        {
            "type": "text_link",
            "offset": 28,
            "length": 4,
            "url": "https://example.com",
        },
    ]


def test_markdown_to_telegram_entities_preserves_ordinary_backslashes() -> None:
    text, entities = markdown_to_telegram_entities(
        "Path C:\\Users\\me and regex \\d+ plus \\.\\+\\(\\) stay intact"
    )

    assert text == "Path C:\\Users\\me and regex \\d+ plus \\.\\+\\(\\) stay intact"
    assert entities == []


def test_markdown_to_telegram_entities_escapes_markdown_punctuation() -> None:
    text, entities = markdown_to_telegram_entities(
        "\\*not italic\\* and \\`not code\\` and \\[link](https://example.com)"
    )

    assert text == "*not italic* and `not code` and [link](https://example.com)"
    assert entities == []


def test_markdown_to_telegram_entities_preserves_non_markdown_escaped_markers() -> None:
    text, entities = markdown_to_telegram_entities("regex \\*\\.py and path foo\\_bar")

    assert text == "regex \\*\\.py and path foo\\_bar"
    assert entities == []


def test_markdown_to_telegram_entities_splits_formatting_around_code() -> None:
    text, entities = markdown_to_telegram_entities(
        "**run `pytest` now**\n# Use `foo` today\n"
    )

    assert text == "run pytest now\nUse foo today\n"
    assert entities == [
        {"type": "code", "offset": 4, "length": 6},
        {"type": "bold", "offset": 0, "length": 3},
        {"type": "bold", "offset": 10, "length": 4},
        {"type": "code", "offset": 19, "length": 3},
        {"type": "bold", "offset": 15, "length": 3},
        {"type": "bold", "offset": 22, "length": 6},
    ]


def test_markdown_to_telegram_entities_links_with_code_labels_are_valid() -> None:
    text, entities = markdown_to_telegram_entities("[`foo`](https://example.com)")

    assert text == "foo"
    assert entities == [
        {
            "type": "text_link",
            "offset": 0,
            "length": 3,
            "url": "https://example.com",
        }
    ]


def test_format_telegram_markdown_chunks_splits_entities() -> None:
    chunks = format_telegram_markdown_chunks("**" + ("a" * 4097) + "**")

    assert chunks == [
        (
            "a" * 4096,
            [{"type": "bold", "offset": 0, "length": 4096}],
        ),
        ("a", [{"type": "bold", "offset": 0, "length": 1}]),
    ]


def test_format_telegram_markdown_chunks_trims_split_entity_trailing_space() -> None:
    chunks = format_telegram_markdown_chunks("**" + ("a" * 4095) + " b**")

    assert chunks == [
        (
            ("a" * 4095) + " ",
            [{"type": "bold", "offset": 0, "length": 4095}],
        ),
        ("b", [{"type": "bold", "offset": 0, "length": 1}]),
    ]


def test_format_telegram_markdown_chunks_trims_multiple_split_entity_whitespace() -> (
    None
):
    chunks = format_telegram_markdown_chunks("```\n" + ("a" * 4093) + "  \nb\n```")

    assert chunks == [
        (
            ("a" * 4093) + "  \n",
            [{"type": "pre", "offset": 0, "length": 4093}],
        ),
        ("b\n", [{"type": "pre", "offset": 0, "length": 1}]),
    ]


def test_format_telegram_markdown_chunks_skips_all_whitespace_split_entity() -> None:
    chunks = format_telegram_markdown_chunks("**" + (" " * 4096) + "a**")

    assert chunks == [
        (" " * 4096, []),
        ("a", [{"type": "bold", "offset": 0, "length": 1}]),
    ]


def test_format_telegram_markdown_chunks_skips_empty_chunks() -> None:
    assert format_telegram_markdown_chunks("") == []
    assert format_telegram_markdown_chunks("```\n```") == []
