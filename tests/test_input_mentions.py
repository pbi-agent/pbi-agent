from __future__ import annotations

from pathlib import Path

import pbi_agent.web.input_mentions as input_mentions
from pbi_agent.web.input_mentions import (
    WorkspaceFileIndex,
    expand_file_mentions,
    expand_input_mentions,
    search_input_mentions,
)


def test_expand_file_mentions_appends_workspace_file_content(tmp_path: Path) -> None:
    target = tmp_path / "report.md"
    target.write_text("hello report\n", encoding="utf-8")

    expanded, warnings = expand_file_mentions(
        "Summarize @report.md",
        root=tmp_path,
    )

    assert warnings == []
    assert expanded == "Summarize report.md"


def test_expand_file_mentions_warns_for_missing_file(tmp_path: Path) -> None:
    expanded, warnings = expand_file_mentions(
        "Summarize @missing.md",
        root=tmp_path,
    )

    assert expanded == "Summarize @missing.md"
    assert warnings == ["Referenced file not found: missing.md"]


def test_expand_file_mentions_ignores_outside_workspace_paths(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    try:
        expanded, warnings = expand_file_mentions(
            f"Check @{outside}",
            root=tmp_path,
        )
    finally:
        outside.unlink(missing_ok=True)

    assert expanded == f"Check @{outside}"
    assert warnings == []


def test_expand_file_mentions_ignores_import_aliases(tmp_path: Path) -> None:
    expanded, warnings = expand_file_mentions(
        'import { Button } from "@/components/ui/button"',
        root=tmp_path,
    )

    assert expanded == 'import { Button } from "@/components/ui/button"'
    assert warnings == []


def test_expand_file_mentions_skips_email_addresses(tmp_path: Path) -> None:
    expanded, warnings = expand_file_mentions(
        "contact me at user@example.com",
        root=tmp_path,
    )

    assert expanded == "contact me at user@example.com"
    assert warnings == []


def test_expand_input_mentions_extracts_image_paths(tmp_path: Path) -> None:
    target = tmp_path / "mockup.png"
    target.write_bytes(b"not-used-by-parser")

    expanded, file_paths, image_paths, warnings = expand_input_mentions(
        "Review @mockup.png carefully",
        root=tmp_path,
    )

    assert expanded == "Review mockup.png carefully"
    assert file_paths == ["mockup.png"]
    assert image_paths == ["mockup.png"]
    assert warnings == []


def test_expand_file_mentions_supports_escaped_spaces(tmp_path: Path) -> None:
    target = tmp_path / "my notes.txt"
    target.write_text("hello notes\n", encoding="utf-8")

    expanded, warnings = expand_file_mentions(
        r"Summarize @my\ notes.txt",
        root=tmp_path,
    )

    assert warnings == []
    assert expanded == "Summarize my notes.txt"


def test_expand_file_mentions_supports_literal_spaces(tmp_path: Path) -> None:
    target = tmp_path / "my notes.txt"
    target.write_text("hello notes\n", encoding="utf-8")

    expanded, warnings = expand_file_mentions(
        "Summarize @my notes.txt please",
        root=tmp_path,
    )

    assert warnings == []
    assert expanded == "Summarize my notes.txt please"


def test_search_input_mentions_returns_ranked_matches(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "docs" / "maintainer.md").write_text("owner\n", encoding="utf-8")
    (tmp_path / "domain.txt").write_text("domain\n", encoding="utf-8")

    results = search_input_mentions("ma", root=tmp_path, limit=10)

    assert [item.path for item in results] == [
        "main.py",
        "docs/maintainer.md",
        "domain.txt",
    ]


def test_search_input_mentions_skips_filtered_directories(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "main.js").write_text("ignored\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")

    results = search_input_mentions("ma", root=tmp_path, limit=10)

    assert [item.path for item in results] == ["main.py"]


def test_workspace_file_index_reuses_cached_file_list(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")

    walk_calls = 0
    original_walk = input_mentions.os.walk

    def counting_walk(*args, **kwargs):
        nonlocal walk_calls
        walk_calls += 1
        return original_walk(*args, **kwargs)

    monkeypatch.setattr(input_mentions.os, "walk", counting_walk)

    index = WorkspaceFileIndex(tmp_path)

    assert [item.path for item in index.search("ma", limit=10)] == ["main.py"]
    assert [item.path for item in index.search("ma", limit=10)] == ["main.py"]
    assert walk_calls == 1
