from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pbi_agent.agent.tool_runtime import execute_tool_calls
from pbi_agent.models.messages import ToolCall
from pbi_agent.tools import explore_workspace as explore_workspace_tool
from pbi_agent.tools.types import ToolContext, ToolOutput


def test_explore_workspace_schema_exposes_approved_parameters_only() -> None:
    properties = explore_workspace_tool.SPEC.parameters_schema["properties"]

    assert set(properties) == {
        "pattern",
        "root",
        "target",
        "regex",
        "path_scope",
        "glob",
        "exclude",
        "mode",
        "context_lines",
        "limit",
        "cursor",
        "start_line",
    }
    assert explore_workspace_tool.SPEC.name == "explore_workspace"
    assert explore_workspace_tool.SPEC.parameters_schema["required"] == ["pattern"]
    assert properties["root"]["oneOf"] == [
        {"type": "string"},
        {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        },
    ]
    assert properties["target"]["enum"] == ["content", "path", "read", "list"]
    assert properties["path_scope"]["enum"] == ["path", "basename"]
    assert properties["mode"]["enum"] == ["files", "snippets", "count"]
    assert "Defaults to true" in properties["regex"]["description"]
    assert "backend" not in properties
    assert "case" not in properties
    assert "result_format" not in properties
    assert "content_or_path" not in properties["target"]["enum"]
    assert "both" not in properties["target"]["enum"]
    assert "max_lines" not in properties


def test_explore_workspace_returns_literal_content_matches(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "service.py").write_text(
        "class UserService:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "other.py").write_text(
        "class TeamService:\n    pass\n", encoding="utf-8"
    )

    result = explore_workspace_tool.handle(
        {"pattern": "UserService", "regex": False}, ToolContext()
    )

    assert result == "service.py"


def test_explore_workspace_supports_regex_and_context(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "service.py").write_text(
        "before\nclass UserService:\nafter\n",
        encoding="utf-8",
    )

    result = explore_workspace_tool.handle(
        {"pattern": r"User\w+", "mode": "snippets", "context_lines": 1},
        ToolContext(),
    )

    assert result == "service.py\n before\n 2:class UserService:\n after"


def test_explore_workspace_context_lines_default_to_snippets_mode(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "service.py").write_text(
        "before\nclass UserService:\nafter\n",
        encoding="utf-8",
    )

    result = explore_workspace_tool.handle(
        {"pattern": "UserService", "regex": False, "context_lines": 1},
        ToolContext(),
    )

    assert result == "service.py\n before\n 2:class UserService:\n after"


def test_explore_workspace_supports_path_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "user_service.py").write_text(
        "class UserService:\n    pass\n",
        encoding="utf-8",
    )

    result = explore_workspace_tool.handle(
        {
            "pattern": "user_service",
            "target": "path",
            "path_scope": "basename",
            "regex": False,
        },
        ToolContext(),
    )

    assert result == "pkg/user_service.py"


def test_explore_workspace_lists_one_directory_level(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "module.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "pkg" / "README.md").write_text("# Notes\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": "pkg", "target": "list", "limit": 10},
        ToolContext(),
    )

    assert isinstance(result, str)
    assert set(result.splitlines()) == {"README.md", "module.py"}


def test_explore_workspace_reads_text_window(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": "notes.txt", "target": "read", "start_line": 2, "limit": 2},
        ToolContext(),
    )

    assert result == "-- more: cursor=4\ntwo\nthree"


def test_explore_workspace_passes_search_options(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    captured: dict[str, Any] = {}

    def fake_explore(pattern: str, **kwargs: Any) -> str:
        captured["pattern"] = pattern
        captured.update(kwargs)
        return "No Match"

    monkeypatch.setattr(explore_workspace_tool, "codetool_explore", fake_explore)

    result = explore_workspace_tool.handle(
        {
            "pattern": "needle",
            "root": "pkg",
            "target": "path",
            "regex": False,
            "path_scope": "basename",
            "glob": ["*.py", "*.md"],
            "exclude": "test_*",
            "mode": "snippets",
            "context_lines": 2,
            "limit": 5,
            "cursor": 10,
        },
        ToolContext(),
    )

    assert result == "No Match"
    assert captured == {
        "pattern": "needle",
        "root": str((tmp_path / "pkg").resolve()),
        "target": "path",
        "regex": False,
        "path_scope": "basename",
        "glob": ["*.py", "*.md"],
        "exclude": "test_*",
        "mode": "snippets",
        "context_lines": 2,
        "limit": 5,
        "cursor": 10,
        "result_format": "text",
    }


def test_explore_workspace_supports_multiple_search_roots(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "service.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "tests" / "test_service.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("needle\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": "needle", "root": ["src", "tests"], "regex": False},
        ToolContext(),
    )

    assert isinstance(result, str)
    assert set(result.splitlines()) == {"src/service.py", "tests/test_service.py"}


def test_explore_workspace_rejects_read_list_multi_root(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("# Notes\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": "README.md", "target": "read", "root": [".", "src"]},
        ToolContext(),
    )

    assert isinstance(result, ToolOutput)
    assert result.is_error is True
    assert result.result == {
        "error": "'root' must be a single path for read/list targets."
    }


def test_explore_workspace_rejects_root_outside_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(workspace)

    result = explore_workspace_tool.handle(
        {"pattern": "needle", "root": str(outside)},
        ToolContext(),
    )

    assert isinstance(result, ToolOutput)
    assert result.is_error is True
    assert result.result == {"error": "'root' must resolve inside the workspace."}


def test_explore_workspace_rejects_read_pattern_outside_root(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("# Notes\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": "../README.md", "target": "read", "root": "src"},
        ToolContext(),
    )

    assert isinstance(result, ToolOutput)
    assert result.is_error is True
    assert result.result == {"error": "'pattern' must resolve inside 'root'."}


def test_explore_workspace_invalid_regex_returns_error_output(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("needle\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": "[", "regex": True},
        ToolContext(),
    )

    assert isinstance(result, ToolOutput)
    assert result.is_error is True
    assert result.result == {
        "error": "invalid regex: unterminated character set at position 0"
    }


def test_explore_workspace_supports_file_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("needle\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": "needle", "root": "notes.txt", "regex": False},
        ToolContext(),
    )

    assert result == "notes.txt"


def test_explore_workspace_reads_supported_image_with_attachment(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    png_bytes = b"\x89PNG\r\n\x1a\nPNGDATA"
    (tmp_path / "chart.png").write_bytes(png_bytes)

    result = explore_workspace_tool.handle(
        {"pattern": "chart.png", "target": "read"},
        ToolContext(),
    )

    assert isinstance(result, ToolOutput)
    assert result.result == {
        "path": "chart.png",
        "mime_type": "image/png",
        "byte_count": len(png_bytes),
    }
    assert len(result.attachments) == 1
    assert result.attachments[0].path == "chart.png"
    assert result.attachments[0].mime_type == "image/png"
    assert result.attachments[0].byte_count == len(png_bytes)


def test_explore_workspace_runtime_returns_raw_text_without_json_wrapper(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("needle\n", encoding="utf-8")

    batch = execute_tool_calls(
        [
            ToolCall(
                call_id="call_explore",
                name="explore_workspace",
                arguments={"pattern": "needle", "regex": False},
            )
        ],
        max_workers=1,
    )

    assert batch.had_errors is False
    assert batch.results[0].output_json == "notes.txt"


def test_explore_workspace_runtime_marks_errors_as_failed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("needle\n", encoding="utf-8")

    batch = execute_tool_calls(
        [
            ToolCall(
                call_id="call_explore",
                name="explore_workspace",
                arguments={"pattern": "[", "regex": True},
            )
        ],
        max_workers=1,
    )

    assert batch.had_errors is True
    assert batch.results[0].is_error is True
    payload = json.loads(batch.results[0].output_json)
    assert payload == {
        "ok": False,
        "result": {"error": "invalid regex: unterminated character set at position 0"},
    }
