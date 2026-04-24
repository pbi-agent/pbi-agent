from __future__ import annotations

import pytest

from pbi_agent.frontmatter import FrontmatterParseError, parse_simple_frontmatter


def test_literal_block_scalars_strip_shared_indent() -> None:
    metadata = parse_simple_frontmatter(
        "description: |\n  line1\n  line2\nname: compress\n",
        block_scalar_keys=frozenset({"description"}),
    )

    assert metadata["description"] == "line1\nline2"


def test_literal_block_scalars_accept_chomping_indicators() -> None:
    metadata = parse_simple_frontmatter(
        "description: |-\n  line1\n  line2\nname: compress\n",
        block_scalar_keys=frozenset({"description"}),
    )

    assert metadata["description"] == "line1\nline2"


def test_folded_block_scalars_accept_chomping_indicators() -> None:
    metadata = parse_simple_frontmatter(
        "description: >-\n  line1\n  line2\nname: compress\n",
        block_scalar_keys=frozenset({"description"}),
    )

    assert metadata["description"] == "line1 line2"


def test_block_scalars_are_rejected_for_disallowed_keys() -> None:
    with pytest.raises(
        FrontmatterParseError,
        match="unsupported block scalar for key 'name'",
    ):
        parse_simple_frontmatter(
            "name: >\n  foo\n  bar\ndescription: ok\n",
            block_scalar_keys=frozenset({"description"}),
        )


def test_include_keys_ignores_unsupported_nested_metadata() -> None:
    metadata = parse_simple_frontmatter(
        (
            "name: vitepress\n"
            "description: VitePress docs skill.\n"
            "metadata:\n"
            "  author: Anthony Fu\n"
            '  version: "2026.1.28"\n'
        ),
        block_scalar_keys=frozenset({"description"}),
        include_keys=frozenset({"name", "description"}),
    )

    assert metadata == {
        "name": "vitepress",
        "description": "VitePress docs skill.",
    }


def test_include_keys_ignores_indentless_sequence_values() -> None:
    metadata = parse_simple_frontmatter(
        (
            "name: compress\n"
            "description: Compression skill.\n"
            "tools:\n"
            "- shell\n"
            "- read_file\n"
        ),
        block_scalar_keys=frozenset({"description"}),
        include_keys=frozenset({"name", "description"}),
    )

    assert metadata == {
        "name": "compress",
        "description": "Compression skill.",
    }
