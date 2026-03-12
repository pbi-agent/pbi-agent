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

    assert result["path"] == "."
    assert result["recursive"] is True
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


def test_list_files_rejects_paths_outside_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent

    result = list_files_tool.handle({"path": str(outside_path)}, ToolContext())

    assert "outside workspace" in result["error"]
