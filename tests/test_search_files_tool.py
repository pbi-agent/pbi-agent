from __future__ import annotations

from contextlib import contextmanager
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
    (tmp_path / "notes" / "one.txt").write_text(
        "alpha\nneedle here\n", encoding="utf-8"
    )
    (tmp_path / "notes" / "two.md").write_text("needle again\n", encoding="utf-8")
    (tmp_path / "notes" / "blob.bin").write_bytes(b"\x00\x01\x02needle")

    result = search_files_tool.handle(
        {"pattern": "needle", "path": "notes"},
        ToolContext(),
    )

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
        },
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


def test_search_files_stops_after_max_matches_without_exhausting_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("needle here\n", encoding="utf-8")
    second.write_text("needle there\n", encoding="utf-8")

    def fake_iter_candidate_files(root: Path, target_path: Path, glob_matcher):
        del root, target_path, glob_matcher
        yield first, "first.txt"
        yield second, "second.txt"

    @contextmanager
    def fake_open_text_file(path: Path, *, encoding: str = "auto"):
        del encoding
        if path == second:
            raise AssertionError("search_files should stop before opening second.txt")
        with path.open("r", encoding="utf-8") as handle:
            yield handle

    monkeypatch.setattr(
        search_files_tool, "_iter_candidate_files", fake_iter_candidate_files
    )
    monkeypatch.setattr(search_files_tool, "open_text_file", fake_open_text_file)

    result = search_files_tool.handle(
        {"pattern": "needle", "max_matches": 1},
        ToolContext(),
    )

    assert result["matches_truncated"] is True
    assert result["matches"] == [
        {
            "path": "first.txt",
            "line_number": 1,
            "line": "needle here",
        }
    ]


def test_search_files_does_not_echo_input_parameters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "one.txt").write_text("needle here\n", encoding="utf-8")

    result = search_files_tool.handle(
        {
            "pattern": "needle",
            "path": "notes",
            "glob": "*.txt",
            "regex": False,
            "max_matches": 20,
        },
        ToolContext(),
    )

    assert "pattern" not in result
    assert "path" not in result
    assert "glob" not in result
    assert "regex" not in result
    assert "searched_files" not in result
    assert "skipped_binary_files" not in result


def test_search_files_skips_filtered_directories_during_recursive_search(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("needle in src\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text(
        "needle in venv\n",
        encoding="utf-8",
    )

    result = search_files_tool.handle(
        {"pattern": "needle", "path": ".", "glob": "*.py", "max_matches": 10},
        ToolContext(),
    )

    assert result["matches"] == [
        {
            "path": "src/app.py",
            "line_number": 1,
            "line": "needle in src",
        }
    ]
