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
