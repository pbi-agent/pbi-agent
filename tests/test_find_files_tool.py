from __future__ import annotations

from pathlib import Path

from pbi_agent.tools import find_files as find_files_tool
from pbi_agent.tools.types import ToolContext


def test_find_files_returns_files_only_in_shallow_first_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README-guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "README-assets").mkdir()

    result = find_files_tool.handle(
        {"path": ".", "glob": "README*", "recursive": True},
        ToolContext(),
    )

    assert result["path"] == "."
    assert result["glob"] == "README*"
    assert result["recursive"] is True
    assert result["returned_entries"] == 2
    assert result["total_entries"] == 2
    assert result["has_more"] is False
    assert result["entries"] == [
        {"path": "README.md", "type": "file"},
        {"path": "docs/README-guide.md", "type": "file"},
    ]


def test_find_files_supports_relative_path_globs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "docs" / "nested").mkdir()
    (tmp_path / "docs" / "nested" / "deep.md").write_text("# Deep\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")

    result = find_files_tool.handle(
        {"path": ".", "glob": "docs/*.md", "recursive": True},
        ToolContext(),
    )

    assert result["entries"] == [{"path": "docs/guide.md", "type": "file"}]


def test_find_files_supports_globstar_for_zero_or_more_path_segments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "docs" / "nested").mkdir()
    (tmp_path / "docs" / "nested" / "deep.md").write_text("# Deep\n", encoding="utf-8")

    result = find_files_tool.handle(
        {"path": ".", "glob": "docs/**/*.md", "recursive": True},
        ToolContext(),
    )

    assert result["entries"] == [
        {"path": "docs/guide.md", "type": "file"},
        {"path": "docs/nested/deep.md", "type": "file"},
    ]


def test_find_files_limits_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README-dev.md").write_text("# Guide\n", encoding="utf-8")

    result = find_files_tool.handle(
        {"path": ".", "glob": "README*", "recursive": True, "max_results": 1},
        ToolContext(),
    )

    assert result["returned_entries"] == 1
    assert result["has_more"] is True
    assert result["entries_truncated"] is True
    assert result["entries"] == [{"path": "README.md", "type": "file"}]


def test_find_files_rejects_paths_outside_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent

    result = find_files_tool.handle(
        {"path": str(outside_path), "glob": "README*"},
        ToolContext(),
    )

    assert "outside workspace" in result["error"]
