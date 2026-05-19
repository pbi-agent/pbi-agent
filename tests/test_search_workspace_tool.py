from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pbi_agent.agent.tool_runtime import execute_tool_calls
from pbi_agent.models.messages import ToolCall
from pbi_agent.tools import search_workspace as search_workspace_tool
from pbi_agent.tools.types import ToolContext, ToolOutput


def test_search_workspace_schema_exposes_approved_parameters_only() -> None:
    properties = search_workspace_tool.SPEC.parameters_schema["properties"]

    assert set(properties) == {
        "pattern",
        "root",
        "regex",
        "target",
        "path_scope",
        "glob",
        "exclude",
        "mode",
        "context_lines",
        "limit",
        "cursor",
    }
    assert search_workspace_tool.SPEC.parameters_schema["required"] == ["pattern"]
    assert "case" not in properties
    assert properties["root"]["oneOf"] == [
        {"type": "string"},
        {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        },
    ]
    assert properties["target"]["enum"] == ["content", "path", "both"]
    assert properties["path_scope"]["enum"] == ["path", "basename"]
    assert properties["mode"]["enum"] == ["files", "snippets", "count"]
    assert "lists matching files/paths" in properties["mode"]["description"]
    assert "backend" not in properties
    assert "result_format" not in properties
    assert "Defaults to false" in properties["regex"]["description"]


def test_search_workspace_returns_literal_matches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "service.py").write_text(
        "class UserService:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "other.py").write_text(
        "class TeamService:\n    pass\n", encoding="utf-8"
    )

    result = search_workspace_tool.handle(
        {"pattern": "UserService", "regex": False}, ToolContext()
    )

    assert result == "service.py"


def test_search_workspace_supports_regex_and_context(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "service.py").write_text(
        "before\nclass UserService:\nafter\n",
        encoding="utf-8",
    )

    result = search_workspace_tool.handle(
        {"pattern": r"User\w+", "regex": True, "mode": "snippets", "context_lines": 1},
        ToolContext(),
    )

    assert result == "service.py\n before\n 2:class UserService:\n after"


def test_search_workspace_context_lines_default_to_snippets_mode(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "service.py").write_text(
        "before\nclass UserService:\nafter\n",
        encoding="utf-8",
    )

    result = search_workspace_tool.handle(
        {"pattern": "UserService", "regex": False, "context_lines": 1},
        ToolContext(),
    )

    assert result == "service.py\n before\n 2:class UserService:\n after"


def test_search_workspace_supports_path_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "user_service.py").write_text(
        "class UserService:\n    pass\n",
        encoding="utf-8",
    )

    result = search_workspace_tool.handle(
        {
            "pattern": "user_service",
            "target": "path",
            "path_scope": "basename",
            "regex": False,
        },
        ToolContext(),
    )

    assert result == "pkg/user_service.py"


def test_search_workspace_supports_find_ls_style_path_listing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "module.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Notes\n", encoding="utf-8")

    result = search_workspace_tool.handle(
        {
            "pattern": ".*",
            "target": "path",
            "regex": True,
            "mode": "files",
            "limit": 10,
        },
        ToolContext(),
    )

    assert isinstance(result, str)
    assert set(result.splitlines()) == {"README.md", "pkg/module.py"}


def test_search_workspace_passes_glob_exclude_and_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()

    captured: dict[str, Any] = {}

    def fake_search(pattern: str, **kwargs: Any) -> str:
        captured["pattern"] = pattern
        captured.update(kwargs)
        return "No Match"

    monkeypatch.setattr(search_workspace_tool, "codetool_search", fake_search)

    result = search_workspace_tool.handle(
        {
            "pattern": "needle",
            "root": "pkg",
            "target": "both",
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
        "target": "both",
        "regex": False,
        "path_scope": "basename",
        "glob": ["*.py", "*.md"],
        "exclude": "test_*",
        "mode": "snippets",
        "context_lines": 2,
        "limit": 5,
        "cursor": 10,
        "result_format": "raw",
    }


def test_search_workspace_supports_multiple_roots(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "service.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "tests" / "test_service.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("needle\n", encoding="utf-8")

    result = search_workspace_tool.handle(
        {"pattern": "needle", "root": ["src", "tests"], "regex": False},
        ToolContext(),
    )

    assert isinstance(result, str)
    assert set(result.splitlines()) == {"src/service.py", "tests/test_service.py"}


def test_search_workspace_rejects_multi_root_outside_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(workspace)

    result = search_workspace_tool.handle(
        {"pattern": "needle", "root": [".", str(outside)]},
        ToolContext(),
    )

    assert isinstance(result, ToolOutput)
    assert result.is_error is True
    assert result.result == {"error": "'root' must resolve inside the workspace."}


def test_search_workspace_supports_cursor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text(
        "needle first\nneedle second\nneedle third\n",
        encoding="utf-8",
    )

    result = search_workspace_tool.handle(
        {
            "pattern": "needle",
            "regex": False,
            "target": "content",
            "mode": "snippets",
            "limit": 1,
            "cursor": 1,
        },
        ToolContext(),
    )

    assert result == "-- more: cursor=2\nnotes.txt:2:needle second"


def test_search_workspace_rejects_root_outside_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(workspace)

    result = search_workspace_tool.handle(
        {"pattern": "needle", "root": str(outside)},
        ToolContext(),
    )

    assert isinstance(result, ToolOutput)
    assert result.is_error is True
    assert result.result == {"error": "'root' must resolve inside the workspace."}


def test_search_workspace_invalid_regex_returns_error_output(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("needle\n", encoding="utf-8")

    result = search_workspace_tool.handle(
        {"pattern": "[", "regex": True},
        ToolContext(),
    )

    assert isinstance(result, ToolOutput)
    assert result.is_error is True
    assert result.result == {
        "error": "invalid regex: unterminated character set at position 0"
    }


def test_search_workspace_supports_file_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("needle\n", encoding="utf-8")

    result = search_workspace_tool.handle(
        {"pattern": "needle", "root": "notes.txt", "regex": False},
        ToolContext(),
    )

    assert result == "notes.txt"


def test_search_workspace_runtime_returns_raw_text_without_json_wrapper(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("needle\n", encoding="utf-8")

    batch = execute_tool_calls(
        [
            ToolCall(
                call_id="call_search",
                name="search_workspace",
                arguments={"pattern": "needle", "regex": False},
            )
        ],
        max_workers=1,
    )

    assert batch.had_errors is False
    assert batch.results[0].output_json == "notes.txt"


def test_search_workspace_runtime_marks_search_errors_as_failed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("needle\n", encoding="utf-8")

    batch = execute_tool_calls(
        [
            ToolCall(
                call_id="call_search",
                name="search_workspace",
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
