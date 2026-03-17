from __future__ import annotations

from pathlib import Path

from pbi_agent.tools import list_files as list_files_tool
from pbi_agent.tools.types import ToolContext


def test_list_files_handles_recursive_listing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    result = list_files_tool.handle(
        {"path": ".", "recursive": True},
        ToolContext(),
    )

    assert result["returned_entries"] == 5
    assert result["total_entries"] == 5
    assert result["has_more"] is False
    assert result["entries"] == [
        {"path": "docs", "type": "directory"},
        {"path": "src", "type": "directory"},
        {"path": "README.md", "type": "file"},
        {"path": "docs/guide.md", "type": "file"},
        {"path": "src/app.py", "type": "file"},
    ]


def test_list_files_limits_entry_count(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for index in range(3):
        (tmp_path / f"file_{index}.txt").write_text("x\n", encoding="utf-8")

    result = list_files_tool.handle(
        {"path": ".", "recursive": False, "max_entries": 2},
        ToolContext(),
    )

    assert len(result["entries"]) == 2
    assert result["returned_entries"] == 2
    assert result["has_more"] is True
    assert result["entries_truncated"] is True
    assert "total_entries" not in result


def test_list_files_supports_file_only_name_globs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README-guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "README-assets").mkdir()

    result = list_files_tool.handle(
        {"path": ".", "glob": "README*", "entry_type": "file", "recursive": True},
        ToolContext(),
    )

    assert result["returned_entries"] == 2
    assert result["total_entries"] == 2
    assert result["entries"] == [
        {"path": "README.md", "type": "file"},
        {"path": "docs/README-guide.md", "type": "file"},
    ]


def test_list_files_does_not_echo_input_parameters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    result = list_files_tool.handle(
        {
            "path": ".",
            "recursive": True,
            "glob": "README.md",
            "entry_type": "file",
            "max_entries": 20,
        },
        ToolContext(),
    )

    assert "path" not in result
    assert "recursive" not in result
    assert "glob" not in result
    assert "entry_type" not in result


def test_list_files_supports_relative_path_globs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "docs" / "nested").mkdir()
    (tmp_path / "docs" / "nested" / "deep.md").write_text("# Deep\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")

    result = list_files_tool.handle(
        {"path": ".", "glob": "docs/*.md", "entry_type": "file", "recursive": True},
        ToolContext(),
    )

    assert result["entries"] == [{"path": "docs/guide.md", "type": "file"}]


def test_list_files_supports_globstar_for_zero_or_more_path_segments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "docs" / "nested").mkdir()
    (tmp_path / "docs" / "nested" / "deep.md").write_text("# Deep\n", encoding="utf-8")

    result = list_files_tool.handle(
        {
            "path": ".",
            "glob": "docs/**/*.md",
            "entry_type": "file",
            "recursive": True,
        },
        ToolContext(),
    )

    assert result["entries"] == [
        {"path": "docs/guide.md", "type": "file"},
        {"path": "docs/nested/deep.md", "type": "file"},
    ]


def test_list_files_skips_filtered_directories_during_recursive_listing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("print('skip')\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.pyc").write_bytes(b"cached")

    result = list_files_tool.handle(
        {"path": ".", "recursive": True, "entry_type": "file", "max_entries": 20},
        ToolContext(),
    )

    assert result["entries"] == [{"path": "src/app.py", "type": "file"}]


def test_list_files_limits_filtered_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README-dev.md").write_text("# Guide\n", encoding="utf-8")

    result = list_files_tool.handle(
        {"path": ".", "glob": "README*", "entry_type": "file", "max_entries": 1},
        ToolContext(),
    )

    assert result["returned_entries"] == 1
    assert result["has_more"] is True
    assert result["entries_truncated"] is True
    assert result["entries"] == [{"path": "README.md", "type": "file"}]


def test_list_files_rejects_invalid_entry_type(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    result = list_files_tool.handle(
        {"path": ".", "entry_type": "bogus"},
        ToolContext(),
    )

    assert "entry_type" in result["error"]


def test_list_files_rejects_paths_outside_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent

    result = list_files_tool.handle({"path": str(outside_path)}, ToolContext())

    assert "outside workspace" in result["error"]
