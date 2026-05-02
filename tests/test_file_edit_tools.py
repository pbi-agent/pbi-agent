from __future__ import annotations

from pathlib import Path

from pbi_agent.tools import replace_in_file, write_file
from pbi_agent.tools.types import ToolContext


def test_write_file_creates_parent_dirs_and_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    context = ToolContext()

    result = write_file.handle(
        {"path": "notes/example.txt", "content": "hello\nworld"},
        context,
    )

    assert result == {
        "status": "completed",
        "message": "write_file succeeded for 'notes/example.txt'",
        "bytes_written": 11,
        "replaced_existing_file": False,
    }
    assert (tmp_path / "notes" / "example.txt").read_text(encoding="utf-8") == (
        "hello\nworld"
    )
    assert context.display_metadata == {
        "operation_type": "create_file",
        "path": "notes/example.txt",
        "diff": "+hello\n+world",
        "diff_line_numbers": [
            {"old": None, "new": 1},
            {"old": None, "new": 2},
        ],
    }


def test_write_file_overwrites_existing_file_with_display_diff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\ngamma", encoding="utf-8")
    context = ToolContext()

    result = write_file.handle(
        {"path": "notes.txt", "content": "alpha\nBETA\ngamma"},
        context,
    )

    assert result["status"] == "completed"
    assert result["replaced_existing_file"] is True
    assert target.read_text(encoding="utf-8") == "alpha\nBETA\ngamma"
    assert context.display_metadata["operation_type"] == "update_file"
    assert context.display_metadata["path"] == "notes.txt"
    assert "-beta" in context.display_metadata["diff"]
    assert "+BETA" in context.display_metadata["diff"]
    assert context.display_metadata["diff_line_numbers"]


def test_replace_in_file_replaces_unique_block_and_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\ngamma", encoding="utf-8")
    context = ToolContext()

    result = replace_in_file.handle(
        {
            "path": "notes.txt",
            "old_string": "alpha\nbeta",
            "new_string": "alpha\nBETA",
        },
        context,
    )

    assert result == {
        "status": "completed",
        "message": "replace_in_file succeeded for 'notes.txt'",
        "replacements": 1,
    }
    assert target.read_text(encoding="utf-8") == "alpha\nBETA\ngamma"
    assert context.display_metadata["operation_type"] == "update_file"
    assert context.display_metadata["path"] == "notes.txt"
    assert "-beta" in context.display_metadata["diff"]
    assert "+BETA" in context.display_metadata["diff"]
    assert context.display_metadata["diff_line_numbers"]


def test_replace_in_file_exact_substring_within_line(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha beta gamma", encoding="utf-8")

    result = replace_in_file.handle(
        {"path": "notes.txt", "old_string": "beta", "new_string": "BETA"},
        ToolContext(),
    )

    assert result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == "alpha BETA gamma"


def test_replace_in_file_requires_unique_match_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\nalpha", encoding="utf-8")

    result = replace_in_file.handle(
        {"path": "notes.txt", "old_string": "alpha", "new_string": "ALPHA"},
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "matched multiple locations" in result["error"]
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\nalpha"


def test_replace_in_file_replace_all(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\nalpha", encoding="utf-8")

    result = replace_in_file.handle(
        {
            "path": "notes.txt",
            "old_string": "alpha",
            "new_string": "ALPHA",
            "replace_all": True,
        },
        ToolContext(),
    )

    assert result["status"] == "completed"
    assert result["replacements"] == 2
    assert target.read_text(encoding="utf-8") == "ALPHA\nbeta\nALPHA"


def test_replace_in_file_trailing_whitespace_fallback_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha  \nbeta", encoding="utf-8")
    context = ToolContext()

    result = replace_in_file.handle(
        {"path": "notes.txt", "old_string": "alpha", "new_string": "ALPHA"},
        context,
    )

    assert result == {
        "status": "completed",
        "message": "replace_in_file succeeded for 'notes.txt'",
        "replacements": 1,
        "warnings": ["used fuzzy old_string match ignoring trailing whitespace"],
    }
    assert target.read_text(encoding="utf-8") == "ALPHA\nbeta"
    assert context.display_metadata["diff_warnings"] == [
        "used fuzzy old_string match ignoring trailing whitespace"
    ]


def test_replace_in_file_trimmed_fallback_after_rstrip_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("  alpha  \nbeta", encoding="utf-8")

    result = replace_in_file.handle(
        {"path": "notes.txt", "old_string": "alpha", "new_string": "ALPHA"},
        ToolContext(),
    )

    assert result["status"] == "completed"
    assert result["warnings"] == [
        "used fuzzy old_string match ignoring leading/trailing whitespace"
    ]
    assert target.read_text(encoding="utf-8") == "ALPHA\nbeta"


def test_replace_in_file_unicode_normalization_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text('message = "smart “quote” – dash"', encoding="utf-8")

    result = replace_in_file.handle(
        {
            "path": "notes.txt",
            "old_string": 'message = "smart "quote" - dash"',
            "new_string": 'message = "plain"',
        },
        ToolContext(),
    )

    assert result["status"] == "completed"
    assert result["warnings"] == [
        "used fuzzy old_string match after normalizing Unicode punctuation/spaces"
    ]
    assert target.read_text(encoding="utf-8") == 'message = "plain"'


def test_replace_in_file_no_match_is_explicit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta", encoding="utf-8")

    result = replace_in_file.handle(
        {"path": "notes.txt", "old_string": "missing", "new_string": "value"},
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "old_string was not found" in result["error"]


def test_file_edit_tools_allow_absolute_paths_outside_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    outside = tmp_path / "outside.txt"

    write_result = write_file.handle(
        {"path": str(outside), "content": "alpha"},
        ToolContext(),
    )
    replace_result = replace_in_file.handle(
        {"path": str(outside), "old_string": "alpha", "new_string": "beta"},
        ToolContext(),
    )

    assert write_result["status"] == "completed"
    assert replace_result["status"] == "completed"
    assert outside.read_text(encoding="utf-8") == "beta"
