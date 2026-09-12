from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

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
    assert "true (default) = regex" in properties["regex"]["description"]
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


def test_explore_workspace_reads_file_root_with_search_hint_pattern(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    styles = tmp_path / "webapp" / "src" / "styles"
    styles.mkdir(parents=True)
    (styles / "modal.css").write_text(
        "one\n.task-form-dialog {}\nthree\n",
        encoding="utf-8",
    )

    result = explore_workspace_tool.handle(
        {
            "pattern": "task-form-dialog",
            "root": "webapp/src/styles/modal.css",
            "target": "read",
            "start_line": 2,
            "limit": 2,
        },
        ToolContext(),
    )

    assert result == ".task-form-dialog {}\nthree"


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


def test_explore_workspace_splits_space_separated_search_root_string(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "pbi_agent").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "pbi_agent" / "service.py").write_text(
        "needle\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_service.py").write_text("needle\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": "needle", "root": "tests src/pbi_agent", "regex": False},
        ToolContext(),
    )

    assert isinstance(result, str)
    assert set(result.splitlines()) == {
        "src/pbi_agent/service.py",
        "tests/test_service.py",
    }


def test_explore_workspace_preserves_existing_search_root_with_spaces(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "my docs").mkdir()
    (tmp_path / "my").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "my docs" / "service.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "my" / "ignored.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "docs" / "ignored.py").write_text("needle\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": "needle", "root": "my docs", "regex": False},
        ToolContext(),
    )

    assert result == "service.py"


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


def test_explore_workspace_allows_read_pattern_outside_root_inside_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("# Notes\n", encoding="utf-8")

    result = explore_workspace_tool.handle(
        {"pattern": str(tmp_path / "README.md"), "target": "read", "root": "src"},
        ToolContext(),
    )

    assert result == "# Notes"


def test_explore_workspace_rejects_read_pattern_outside_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("# Notes\n", encoding="utf-8")
    monkeypatch.chdir(workspace)

    result = explore_workspace_tool.handle(
        {"pattern": str(outside), "target": "read"},
        ToolContext(),
    )

    assert isinstance(result, ToolOutput)
    assert result.is_error is True
    assert result.result == {"error": "'pattern' must resolve inside the workspace."}


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


def test_missing_list_recovers_reported_filename(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_openai_provider.py").write_text("must not read this")
    result = explore_workspace_tool.handle(
        {
            "limit": 30,
            "pattern": "test_openai_provider",
            "root": "tests",
            "target": "list",
        },
        ToolContext(workspace_root=tmp_path),
    )

    assert isinstance(result, ToolOutput)
    assert not result.is_error
    assert result.result == (
        "List target not found; matching file paths under tests:\n"
        "tests/test_openai_provider.py"
    )
    assert result.attachments == []
    assert result.display_metadata == {
        "requested_target": "list",
        "effective_target": "path",
        "recovery_reason": "missing_list_target",
        "truncated": False,
        "next_cursor": None,
        "continuation": None,
    }


@pytest.mark.parametrize("directory", [True, False])
def test_existing_list_target_takes_precedence(tmp_path: Path, directory: bool) -> None:
    exact = tmp_path / "needle"
    if directory:
        exact.mkdir()
        (exact / "child.py").touch()
    else:
        exact.touch()
    (tmp_path / "needle.py").touch()
    result = explore_workspace_tool.handle(
        {"pattern": "needle", "target": "list"}, ToolContext(workspace_root=tmp_path)
    )
    assert result == ("child.py" if directory else "needle")


def test_existing_list_cursor_and_file_root_remain_valid(tmp_path: Path) -> None:
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    context = ToolContext(workspace_root=tmp_path)
    assert (
        explore_workspace_tool.handle(
            {"pattern": ".", "target": "list", "limit": 1, "cursor": "1"}, context
        )
        == "b.py"
    )
    assert (
        explore_workspace_tool.handle(
            {"pattern": ".", "root": "a.py", "target": "list"}, context
        )
        == "a.py"
    )


def test_existing_list_library_failure_does_not_recover(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []

    def explore(pattern: str, **kwargs: Any):
        calls.append(kwargs["target"])
        raise ValueError("listing failed")

    monkeypatch.setattr(explore_workspace_tool, "codetool_explore", explore)
    result = explore_workspace_tool.handle(
        {"pattern": ".", "target": "list"}, ToolContext(workspace_root=tmp_path)
    )
    assert isinstance(result, ToolOutput)
    assert result.is_error
    assert result.result == {"error": "listing failed"}
    assert calls == ["list"]


def test_missing_list_allows_internal_symlink_root_and_literal_filename(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "my tests"
    tests.mkdir()
    (tests / "needle.py.bak").touch()
    (tests / "needleXpy.bak").touch()
    (tmp_path / "linked").symlink_to(tests, target_is_directory=True)
    result = explore_workspace_tool.handle(
        {"pattern": "needle.py", "root": "linked", "target": "list"},
        ToolContext(workspace_root=tmp_path),
    )
    assert isinstance(result, ToolOutput)
    assert not result.is_error
    assert result.result == (
        "List target not found; matching file paths under my tests:\n"
        "my tests/needle.py.bak"
    )


def test_missing_list_no_matches_stays_under_requested_root(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "needle.py").touch()
    result = explore_workspace_tool.handle(
        {"pattern": "needle", "root": "tests", "target": "list"},
        ToolContext(workspace_root=tmp_path),
    )
    assert isinstance(result, ToolOutput)
    assert not result.is_error
    assert result.result == (
        "List target not found; no matching file paths found under tests."
    )


@pytest.mark.parametrize("backend", ["auto", "python"])
def test_missing_list_filters_multiple_matches_and_symlinks(
    tmp_path: Path, monkeypatch, backend: str
) -> None:
    workspace = tmp_path / "workspace"
    tests = workspace / "tests"
    tests.mkdir(parents=True)
    (tests / ".gitignore").write_text("ignored/\nneedle_ignored.py\n")
    for name in (
        "needle.py",
        "needle_extra.py",
        "needle.md",
        "needle_excluded.py",
        "needle_ignored.py",
        "ignored/needle.py",
        "nested/needle.py",
    ):
        path = tests / name
        path.parent.mkdir(exist_ok=True)
        path.touch()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "needle_secret.py").touch()
    (tests / "needle_link.py").symlink_to(outside / "needle_secret.py")
    (tests / "linked").symlink_to(outside, target_is_directory=True)
    (tests / "needle_broken.py").symlink_to(outside / "absent.py")
    real_explore = explore_workspace_tool.codetool_explore
    calls: list[dict[str, Any]] = []

    def explore(pattern: str, **kwargs: Any):
        calls.append(kwargs)
        return real_explore(pattern, **kwargs, backend=backend)

    monkeypatch.setattr(explore_workspace_tool, "codetool_explore", explore)
    result = explore_workspace_tool.handle(
        {
            "pattern": "needle",
            "root": "tests",
            "target": "list",
            "regex": False,
            "glob": ["*.py"],
            "exclude": ["*excluded*"],
        },
        ToolContext(workspace_root=workspace),
    )
    assert isinstance(result, ToolOutput)
    assert not result.is_error
    assert isinstance(result.result, str)
    assert set(result.result.splitlines()[1:]) == {
        "tests/needle.py",
        "tests/needle_extra.py",
        "tests/nested/needle.py",
    }
    assert len(calls) == 1
    assert calls[0]["target"] == "path"
    assert calls[0]["regex"] is False
    assert calls[0]["path_scope"] == "basename"
    assert calls[0]["mode"] == "files"
    assert calls[0]["cursor"] is None
    assert calls[0]["result_format"] == "full"


def test_missing_list_pagination_continues_as_path_search(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    for name in ("needle.py", "needle_extra.py", "needle_last.py", "needle.md"):
        (tests / name).touch()
    context = ToolContext(workspace_root=tmp_path)
    result = explore_workspace_tool.handle(
        {
            "pattern": "needle",
            "root": "tests",
            "target": "list",
            "limit": 1,
            "glob": "*.py",
            "exclude": "*last*",
        },
        context,
    )
    assert isinstance(result, ToolOutput)
    assert not result.is_error
    assert result.display_metadata["truncated"] is True
    assert result.display_metadata["next_cursor"] == "1"
    assert isinstance(result.result, str)
    lines = result.result.splitlines()
    assert lines[1] == "tests/needle.py"
    assert len(lines) == 3
    assert 'continue with target="path" (not "list")' in lines[2]
    continuation = json.loads(lines[2].split(": ", 1)[1])
    assert (
        continuation
        == result.display_metadata["continuation"]
        == {
            "pattern": "needle",
            "root": "tests",
            "target": "path",
            "path_scope": "basename",
            "regex": False,
            "mode": "files",
            "limit": 1,
            "glob": "*.py",
            "exclude": "*last*",
            "cursor": "1",
        }
    )
    assert explore_workspace_tool.handle(continuation, context) == "needle_extra.py"


@pytest.mark.parametrize("limit,expected", [(None, 50), (2, 2), (5000, 1000)])
def test_missing_list_preserves_limit_normalization(
    tmp_path: Path, monkeypatch, limit: int | None, expected: int
) -> None:
    captured: dict[str, Any] = {}

    def explore(pattern: str, **kwargs: Any):
        captured.update(kwargs)
        return {"matches": [], "truncated": False, "next_cursor": None}

    monkeypatch.setattr(explore_workspace_tool, "codetool_explore", explore)
    arguments: dict[str, Any] = {"pattern": "needle", "target": "list"}
    if limit is not None:
        arguments["limit"] = limit
    result = explore_workspace_tool.handle(
        arguments, ToolContext(workspace_root=tmp_path)
    )
    assert isinstance(result, ToolOutput)
    assert not result.is_error
    assert captured["limit"] == expected


@pytest.mark.parametrize(
    "overrides",
    [
        {"target": "read"},
        {"root": "missing"},
        {"root": "needle.py"},
        {"root": ["tests"]},
        {"root": 7},
        {"root": ""},
        {"regex": True},
        {"regex": "false"},
        {"regex": None},
        {"cursor": 0},
        {"cursor": "1"},
        {"cursor": ""},
        {"cursor": None},
        {"cursor": False},
        {"pattern": "needle/"},
        {"pattern": "nested/needle"},
        {"pattern": r"nested\needle"},
        {"pattern": "../needle"},
        {"pattern": r"..\needle"},
        {"pattern": "./needle"},
        {"pattern": r"C:\needle"},
        {"pattern": "needle*"},
        {"pattern": "needle?"},
        {"pattern": "needle[ab]"},
        {"pattern": "needle.*"},
        {"pattern": "^needle"},
        {"pattern": "needle$"},
        {"pattern": "(needle)"},
        {"pattern": "needle|other"},
        {"pattern": "needle+"},
        {"pattern": "needle{1}"},
        {"pattern": "needle..py"},
        {"pattern": ""},
        {"limit": "30"},
        {"limit": True},
        {"limit": 0},
        {"limit": -1},
        {"limit": None},
        {"glob": 7},
        {"glob": ["*.py", 7]},
        {"exclude": {"glob": "*.py"}},
        {"context_lines": -1},
        {"start_line": False},
        {"mode": "unknown"},
        {"path_scope": "unknown"},
        {"unknown": True},
    ],
)
def test_missing_list_ineligible_calls_never_search(
    tmp_path: Path, monkeypatch, overrides: dict[str, Any]
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "needle.py").touch()

    def unexpected_explore(*args, **kwargs):
        pytest.fail("ineligible list/read must not search")

    monkeypatch.setattr(explore_workspace_tool, "codetool_explore", unexpected_explore)
    result = explore_workspace_tool.handle(
        {"pattern": "needle", "target": "list", **overrides},
        ToolContext(workspace_root=tmp_path),
    )
    assert isinstance(result, ToolOutput)
    assert result.is_error
    assert result.display_metadata == {}


@pytest.mark.parametrize("pattern", [".", "..", " "])
def test_dot_list_targets_keep_exact_semantics(
    tmp_path: Path, monkeypatch, pattern: str
) -> None:
    calls: list[str] = []

    def explore(pattern: str, **kwargs: Any):
        calls.append(kwargs["target"])
        return "exact listing"

    monkeypatch.setattr(explore_workspace_tool, "codetool_explore", explore)
    result = explore_workspace_tool.handle(
        {"pattern": pattern, "target": "list"}, ToolContext(workspace_root=tmp_path)
    )
    if pattern in {".", " "}:
        assert result == "exact listing"
        assert calls == ["list"]
    else:
        assert isinstance(result, ToolOutput)
        assert result.is_error
        assert calls == []


@pytest.mark.parametrize(
    "kind", ["absolute", "root_escape", "target_escape", "dangling"]
)
def test_missing_list_path_and_symlink_guards(
    tmp_path: Path, monkeypatch, kind: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "needle.py").touch()
    arguments = {"pattern": "needle", "target": "list"}
    if kind == "absolute":
        arguments["pattern"] = str(workspace / "needle")
    elif kind == "root_escape":
        (workspace / "linked").symlink_to(outside, target_is_directory=True)
        arguments["root"] = "linked"
    elif kind == "target_escape":
        (workspace / "needle").symlink_to(outside / "missing")
    else:
        (workspace / "needle").symlink_to(workspace / "missing")

    def unexpected_explore(*args, **kwargs):
        pytest.fail("unsafe or ineligible list must not search")

    monkeypatch.setattr(explore_workspace_tool, "codetool_explore", unexpected_explore)
    result = explore_workspace_tool.handle(
        arguments, ToolContext(workspace_root=workspace)
    )
    assert isinstance(result, ToolOutput)
    assert result.is_error


@pytest.mark.parametrize("stage", ["root_stat", "target_stat", "scandir", "search"])
def test_missing_list_permission_errors_stay_errors(
    tmp_path: Path, monkeypatch, stage: str
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    calls = 0

    def explore(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise PermissionError("denied")

    monkeypatch.setattr(explore_workspace_tool, "codetool_explore", explore)
    if stage in {"root_stat", "target_stat"}:
        original_stat = Path.stat
        denied = tests if stage == "root_stat" else tests / "needle"

        def stat(path, *args, **kwargs):
            if path == denied:
                raise PermissionError("denied")
            return original_stat(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", stat)
    elif stage == "scandir":

        def scandir(*args, **kwargs):
            raise PermissionError("denied")

        monkeypatch.setattr(explore_workspace_tool.os, "scandir", scandir)
    result = explore_workspace_tool.handle(
        {"pattern": "needle", "root": "tests", "target": "list"},
        ToolContext(workspace_root=tmp_path),
    )
    assert isinstance(result, ToolOutput)
    assert result.is_error
    assert result.result == {"error": "denied"}
    assert calls == (1 if stage == "search" else 0)


@pytest.mark.parametrize("kind", ["symlink", "absolute", "traversal"])
def test_missing_list_checks_backend_result_confinement(
    tmp_path: Path, monkeypatch, kind: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "secret.py"
    outside.touch()
    (workspace / "needle.py").symlink_to(outside)

    def explore(*args, **kwargs):
        path = {
            "symlink": "needle.py",
            "absolute": str(outside),
            "traversal": "../secret.py",
        }[kind]
        return {"matches": [{"path": path}]}

    monkeypatch.setattr(explore_workspace_tool, "codetool_explore", explore)
    result = explore_workspace_tool.handle(
        {"pattern": "needle", "target": "list"}, ToolContext(workspace_root=workspace)
    )
    assert isinstance(result, ToolOutput)
    assert result.is_error
    expected = (
        "search result must resolve inside the workspace."
        if kind == "symlink"
        else "search result must be under its root."
    )
    assert result.result == {"error": expected}
    assert "secret.py" not in str(result.result)


def test_missing_list_runtime_preserves_text_and_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "needle.py").touch()
    tracer = Mock()
    batch = execute_tool_calls(
        [
            ToolCall(
                call_id="recovery",
                name="explore_workspace",
                arguments={"pattern": "needle", "target": "list"},
            )
        ],
        max_workers=1,
        context=ToolContext(tracer=tracer),
    )
    assert not batch.had_errors
    assert batch.results[0].output_json == (
        "List target not found; matching file paths under .:\nneedle.py"
    )
    assert batch.results[0].display_metadata["effective_target"] == "path"
    tracer.log_tool_call.assert_called_once()
    assert tracer.log_tool_call.call_args.kwargs["metadata"] == {
        **batch.results[0].display_metadata,
        "attachment_count": 0,
    }


def test_explore_guidance_distinguishes_filename_search_from_listing() -> None:
    spec = explore_workspace_tool.SPEC
    assert 'Partial filenames: target="path".' in spec.description
    assert 'Existing exact file/directory: target="list".' in spec.description
    assert spec.prompt_usage is not None
    assert '{"pattern": ".", "root": "tests", "target": "list"}' in spec.prompt_usage
    assert (
        '{"pattern": "test_openai_provider", "root": "tests", "target": "path", "regex": false}'
        in spec.prompt_usage
    )
