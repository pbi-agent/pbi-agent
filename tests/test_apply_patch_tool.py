from __future__ import annotations

from pathlib import Path


from pbi_agent.tools import apply_patch as apply_patch_tool
from pbi_agent.tools.output import MAX_OUTPUT_CHARS
from pbi_agent.tools.types import ToolContext


def test_apply_patch_handle_create_update_and_delete_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    create_result = apply_patch_tool.handle(
        {
            "operation_type": "create_file",
            "path": "notes/example.txt",
            "diff": "+hello\n+world",
        },
        ToolContext(),
    )

    created_file = tmp_path / "notes" / "example.txt"
    assert create_result["status"] == "completed"
    assert created_file.read_text(encoding="utf-8") == "hello\nworld"

    update_result = apply_patch_tool.handle(
        {
            "operation_type": "update_file",
            "path": "notes/example.txt",
            "diff": " hello\n-world\n+there",
        },
        ToolContext(),
    )

    assert update_result["status"] == "completed"
    assert created_file.read_text(encoding="utf-8") == "hello\nthere"

    delete_result = apply_patch_tool.handle(
        {
            "operation_type": "delete_file",
            "path": "notes/example.txt",
        },
        ToolContext(),
    )

    assert delete_result["status"] == "completed"
    assert not created_file.exists()


def test_apply_patch_handle_update_file_accepts_unified_diff_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes" / "example.txt"
    target.parent.mkdir()
    target.write_text("hello\nworld\n", encoding="utf-8")

    result = apply_patch_tool.handle(
        {
            "operation_type": "update_file",
            "path": "notes/example.txt",
            "diff": (
                "--- a/notes/example.txt\n"
                "+++ b/notes/example.txt\n"
                "@@ -1,2 +1,2 @@\n"
                " hello\n"
                "-world\n"
                "+there"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == "hello\nthere\n"


def test_apply_patch_handle_stores_display_line_numbers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes" / "example.txt"
    target.parent.mkdir()
    target.write_text("alpha\nbeta\ngamma\ndelta", encoding="utf-8")
    context = ToolContext()

    result = apply_patch_tool.handle(
        {
            "operation_type": "update_file",
            "path": "notes/example.txt",
            "diff": " gamma\n-delta\n+DELTA",
        },
        context,
    )

    assert result["status"] == "completed"
    assert "diff_line_numbers" not in result
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\ngamma\nDELTA"
    assert context.display_metadata == {
        "diff": " gamma\n-delta\n+DELTA",
        "diff_line_numbers": [
            {"old": 3, "new": 3},
            {"old": 4, "new": None},
            {"old": None, "new": 4},
        ],
    }


def test_apply_patch_handle_unified_diff_display_metadata_uses_v4a_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes" / "example.txt"
    target.parent.mkdir()
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    context = ToolContext()

    result = apply_patch_tool.handle(
        {
            "operation_type": "update_file",
            "path": "notes/example.txt",
            "diff": (
                "--- a/notes/example.txt\n"
                "+++ b/notes/example.txt\n"
                "@@ -2,2 +2,2 @@\n"
                " beta\n"
                "-gamma\n"
                "+GAMMA"
            ),
        },
        context,
    )

    assert result["status"] == "completed"
    assert context.display_metadata == {
        "diff": "@@\n beta\n-gamma\n+GAMMA",
        "diff_line_numbers": [
            {"old": None, "new": None},
            {"old": 2, "new": 2},
            {"old": 3, "new": None},
            {"old": None, "new": 3},
        ],
    }


def test_apply_patch_handle_create_file_accepts_unified_diff_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = apply_patch_tool.handle(
        {
            "operation_type": "create_file",
            "path": "notes/example.txt",
            "diff": (
                "--- /dev/null\n"
                "+++ b/notes/example.txt\n"
                "@@ -0,0 +1,2 @@\n"
                "+hello\n"
                "+world"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "completed"
    assert (tmp_path / "notes" / "example.txt").read_text(encoding="utf-8") == (
        "hello\nworld"
    )


def test_apply_patch_handle_create_file_replaces_existing_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes" / "example.txt"
    target.parent.mkdir()
    target.write_text("old\ncontent", encoding="utf-8")

    result = apply_patch_tool.handle(
        {
            "operation_type": "create_file",
            "path": "notes/example.txt",
            "diff": "+new\n+content",
        },
        ToolContext(),
    )

    assert result == {
        "status": "completed",
        "message": "file exists and was replaced: 'notes/example.txt'",
    }
    assert target.read_text(encoding="utf-8") == "new\ncontent"


def test_apply_patch_handle_unified_diff_fallback_reports_conversion_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("hello\nworld", encoding="utf-8")

    result = apply_patch_tool.handle(
        {
            "operation_type": "update_file",
            "path": "notes.txt",
            "diff": (
                "--- a/notes.txt\n"
                "+++ b/notes.txt\n"
                "@@ -1,2 +1,2 @@\n"
                " hello\n"
                "-missing\n"
                "+there"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "Received unified diff syntax" in result["error"]
    assert "Use a V4A body" in result["error"]


def test_apply_patch_handle_update_file_strips_accidental_leading_blank_line(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "TODO.md"
    target.write_text(
        "[X] Add focused tests and validate\n[X] Update memory",
        encoding="utf-8",
    )

    result = apply_patch_tool.handle(
        {
            "operation_type": "update_file",
            "path": "TODO.md",
            "diff": (
                "\n"
                " [X] Add focused tests and validate\n"
                " [X] Update memory\n"
                "+\n"
                "+<!-- Test comment: apply_patch tool is working! -->"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == (
        "[X] Add focused tests and validate\n"
        "[X] Update memory\n"
        "\n"
        "<!-- Test comment: apply_patch tool is working! -->"
    )


def test_apply_patch_handle_update_file_reports_leading_blank_line_hint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("hello\nworld", encoding="utf-8")

    result = apply_patch_tool.handle(
        {
            "operation_type": "update_file",
            "path": "notes.txt",
            "diff": "\n missing\n+there",
        },
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "V4A diff begins with an empty context line" in result["error"]
    assert "remove the leading blank line" in result["error"]


def test_apply_patch_handle_rejects_paths_outside_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent / "escape.txt"

    result = apply_patch_tool.handle(
        {
            "operation_type": "create_file",
            "path": str(outside_path),
            "diff": "+secret",
        },
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "outside workspace" in result["error"]


def test_apply_patch_handle_validates_required_arguments() -> None:
    missing_path = apply_patch_tool.handle(
        {
            "operation_type": "create_file",
            "path": "",
            "diff": "+hello",
        },
        ToolContext(),
    )
    unsupported_operation = apply_patch_tool.handle(
        {
            "operation_type": "rename_file",
            "path": "example.txt",
        },
        ToolContext(),
    )

    assert missing_path == {"error": "'path' must be a non-empty string."}
    assert unsupported_operation == {
        "error": "Unsupported operation_type 'rename_file'."
    }


def test_apply_patch_handle_bounds_long_error_output(monkeypatch) -> None:
    def raise_long_error(path: Path, diff: str | None) -> None:
        del path, diff
        raise ValueError(f"start-{'x' * (MAX_OUTPUT_CHARS + 200)}-end")

    monkeypatch.setattr(apply_patch_tool, "_create_file", raise_long_error)

    result = apply_patch_tool.handle(
        {
            "operation_type": "create_file",
            "path": "notes/example.txt",
            "diff": "+hello",
        },
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert len(result["error"]) <= MAX_OUTPUT_CHARS
    assert result["error"].startswith("start-")
    assert result["error"].endswith("-end")
    assert "chars omitted" in result["error"]
