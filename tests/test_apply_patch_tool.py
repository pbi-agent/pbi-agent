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
            "patch": (
                "*** Begin Patch\n"
                "*** Add File: notes/example.txt\n"
                "+hello\n"
                "+world\n"
                "*** End Patch"
            ),
        },
        ToolContext(),
    )

    created_file = tmp_path / "notes" / "example.txt"
    assert create_result["status"] == "completed"
    assert created_file.read_text(encoding="utf-8") == "hello\nworld"

    update_result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: notes/example.txt\n"
                "@@\n"
                " hello\n"
                "-world\n"
                "+there\n"
                "*** End Patch"
            ),
        },
        ToolContext(),
    )

    assert update_result["status"] == "completed"
    assert created_file.read_text(encoding="utf-8") == "hello\nthere"

    delete_result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n*** Delete File: notes/example.txt\n*** End Patch"
            ),
        },
        ToolContext(),
    )

    assert delete_result["status"] == "completed"
    assert not created_file.exists()


def test_apply_patch_handle_multi_file_patch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "first.txt").write_text("one\ntwo", encoding="utf-8")

    result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: first.txt\n"
                "@@\n"
                " one\n"
                "-two\n"
                "+TWO\n"
                "*** Add File: second.txt\n"
                "+new\n"
                "*** End Patch"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "completed"
    assert result["operations"] == [
        {"operation_type": "update_file", "path": "first.txt"},
        {"operation_type": "create_file", "path": "second.txt"},
    ]
    assert (tmp_path / "first.txt").read_text(encoding="utf-8") == "one\nTWO"
    assert (tmp_path / "second.txt").read_text(encoding="utf-8") == "new"


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
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: notes/example.txt\n"
                "@@\n"
                " gamma\n"
                "-delta\n"
                "+DELTA\n"
                "*** End Patch"
            ),
        },
        context,
    )

    assert result["status"] == "completed"
    assert "diff_line_numbers" not in result
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\ngamma\nDELTA"
    assert context.display_metadata == {
        "operation_type": "update_file",
        "path": "notes/example.txt",
        "diff": "@@\n gamma\n-delta\n+DELTA",
        "diff_line_numbers": [
            {"old": None, "new": None},
            {"old": 3, "new": 3},
            {"old": 4, "new": None},
            {"old": None, "new": 4},
        ],
    }


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
            "patch": (
                "*** Begin Patch\n"
                "*** Add File: notes/example.txt\n"
                "+new\n"
                "+content\n"
                "*** End Patch"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "completed"
    assert result["operations"] == [
        {
            "operation_type": "create_file",
            "path": "notes/example.txt",
            "replaced_existing_file": True,
        }
    ]
    assert target.read_text(encoding="utf-8") == "new\ncontent"


def test_apply_patch_handle_create_file_stores_normalized_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    context = ToolContext()

    result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Add File: notes/example.txt\n"
                "+hello\n"
                "+world\n"
                "*** End Patch"
            ),
        },
        context,
    )

    assert result["status"] == "completed"
    assert context.display_metadata == {
        "operation_type": "create_file",
        "path": "notes/example.txt",
        "diff": "+hello\n+world",
        "diff_line_numbers": [
            {"old": None, "new": 1},
            {"old": None, "new": 2},
        ],
    }


def test_apply_patch_handle_rejects_unified_diff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("hello\nworld\n", encoding="utf-8")

    result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: notes.txt\n"
                "--- a/notes.txt\n"
                "+++ b/notes.txt\n"
                "@@ -1,2 +1,2 @@\n"
                " hello\n"
                "-world\n"
                "+there\n"
                "*** End Patch"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "Unified diff syntax is not supported by apply_patch" in result["error"]
    assert target.read_text(encoding="utf-8") == "hello\nworld\n"


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

    context = ToolContext()

    result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: TODO.md\n"
                "\n"
                " [X] Add focused tests and validate\n"
                " [X] Update memory\n"
                "+\n"
                "+<!-- Test comment: apply_patch tool is working! -->\n"
                "*** End Patch"
            ),
        },
        context,
    )

    assert result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == (
        "[X] Add focused tests and validate\n"
        "[X] Update memory\n"
        "\n"
        "<!-- Test comment: apply_patch tool is working! -->"
    )
    assert context.display_metadata["diff"] == (
        " [X] Add focused tests and validate\n"
        " [X] Update memory\n"
        "+\n"
        "+<!-- Test comment: apply_patch tool is working! -->"
    )


def test_apply_patch_handle_metadata_does_not_reapply_raw_diff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    context = ToolContext()
    calls = 0
    original_apply = apply_patch_tool._apply_v4a_diff

    def count_apply(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_apply(*args, **kwargs)

    monkeypatch.setattr(
        apply_patch_tool,
        "_apply_v4a_diff",
        count_apply,
    )

    result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: notes.txt\n"
                "@@\n"
                " alpha\n"
                "-beta\n"
                "+BETA\n"
                "*** End Patch"
            ),
        },
        context,
    )

    assert result["status"] == "completed"
    assert calls == 1
    assert context.display_metadata["diff"] == "@@\n alpha\n-beta\n+BETA"


def test_apply_patch_handle_fuzzy_match_stores_warning_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha  \nbeta\n", encoding="utf-8")
    context = ToolContext()

    result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: notes.txt\n"
                "@@\n"
                "-alpha\n"
                "+BETA\n"
                "*** End Patch"
            ),
        },
        context,
    )

    assert result["status"] == "completed"
    assert result["operations"] == [
        {
            "operation_type": "update_file",
            "path": "notes.txt",
            "warnings": ["used fuzzy context match ignoring trailing whitespace"],
        }
    ]
    assert target.read_text(encoding="utf-8") == "BETA\nbeta\n"
    assert context.display_metadata["diff_warnings"] == [
        "used fuzzy context match ignoring trailing whitespace"
    ]


def test_apply_patch_handle_update_file_reports_leading_blank_line_hint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("hello\nworld", encoding="utf-8")

    result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: notes.txt\n"
                "\n"
                " missing\n"
                "+there\n"
                "*** End Patch"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "V4A hunk begins with an empty context line" in result["error"]
    assert "remove the leading blank line" in result["error"]


def test_apply_patch_handle_rejects_paths_outside_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent / "escape.txt"

    result = apply_patch_tool.handle(
        {
            "patch": (
                f"*** Begin Patch\n*** Add File: {outside_path}\n+secret\n*** End Patch"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "patch paths must be relative" in result["error"]


def test_apply_patch_handle_rejects_missing_envelope() -> None:
    result = apply_patch_tool.handle(
        {"patch": "*** Add File: example.txt\n+hello"},
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "patch must start with '*** Begin Patch'" in result["error"]


def test_apply_patch_handle_rejects_move_operations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "old.txt").write_text("hello", encoding="utf-8")

    result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: old.txt\n"
                "*** Move to: new.txt\n"
                "@@\n"
                " hello\n"
                "*** End Patch"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert "Move/rename operations are not supported yet" in result["error"]


def test_apply_patch_handle_validates_required_arguments() -> None:
    missing_patch = apply_patch_tool.handle(
        {"patch": ""},
        ToolContext(),
    )

    assert missing_patch == {"error": "'patch' must be a non-empty string."}


def test_apply_patch_handle_bounds_long_error_output(monkeypatch) -> None:
    def raise_long_error(path: Path, diff: str | None) -> None:
        del path, diff
        raise ValueError(f"start-{'x' * (MAX_OUTPUT_CHARS + 200)}-end")

    monkeypatch.setattr(apply_patch_tool, "_create_file", raise_long_error)

    result = apply_patch_tool.handle(
        {
            "patch": (
                "*** Begin Patch\n"
                "*** Add File: notes/example.txt\n"
                "+hello\n"
                "*** End Patch"
            ),
        },
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert len(result["error"]) <= MAX_OUTPUT_CHARS
    assert result["error"].startswith("start-")
    assert result["error"].endswith("-end")
    assert "chars omitted" in result["error"]
