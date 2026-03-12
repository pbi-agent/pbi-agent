from __future__ import annotations

from pathlib import Path

from pbi_agent.tools import search_files as search_files_tool
from pbi_agent.tools.output import MAX_OUTPUT_CHARS
from pbi_agent.tools.types import ToolContext


def test_search_files_finds_matches_and_skips_binary_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "one.txt").write_text("alpha\nneedle here\n", encoding="utf-8")
    (tmp_path / "notes" / "two.md").write_text("needle again\n", encoding="utf-8")
    (tmp_path / "notes" / "blob.bin").write_bytes(b"\x00\x01\x02needle")

    result = search_files_tool.handle(
        {"pattern": "needle", "path": "notes"},
        ToolContext(),
    )

    assert result["pattern"] == "needle"
    assert result["path"] == "notes"
    assert result["glob"] is None
    assert result["regex"] is False
    assert result["searched_files"] == 3
    assert result["skipped_binary_files"] == 1
    assert result["matches"] == [
        {
            "path": "notes/one.txt",
            "line_number": 2,
            "line": "needle here",
        },
        {
            "path": "notes/two.md",
            "line_number": 1,
            "line": "needle again",
        }
    ]


def test_search_files_supports_regex_and_bounds_long_match_lines(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    long_line = f"prefix-{'x' * (MAX_OUTPUT_CHARS + 200)}-suffix"
    (tmp_path / "report.txt").write_text(f"{long_line}\nitem-42\n", encoding="utf-8")

    result = search_files_tool.handle(
        {"pattern": r"item-\d+|prefix-", "regex": True, "max_matches": 1},
        ToolContext(),
    )

    assert result["matches_truncated"] is True
    match = result["matches"][0]
    assert match["path"] == "report.txt"
    assert match["line_truncated"] is True
    assert len(match["line"]) <= MAX_OUTPUT_CHARS
    assert match["line"].startswith("prefix-")
    assert match["line"].endswith("-suffix")
    assert "chars omitted" in match["line"]


def test_search_files_rejects_paths_outside_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent

    result = search_files_tool.handle(
        {"pattern": "needle", "path": str(outside_path)},
        ToolContext(),
    )

    assert "outside workspace" in result["error"]
