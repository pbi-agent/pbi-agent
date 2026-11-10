from __future__ import annotations

from pathlib import Path

import pytest

from pbi_agent.config import CommandConfig, ModelProfileConfig, Settings
from pbi_agent.tools import read_image
from pbi_agent.tools.availability import (
    BUILTIN_TOOL_CATEGORIES,
    effective_excluded_tool_names,
    normalize_tool_categories,
)
from pbi_agent.tools.types import ToolContext, ToolOutput

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _run(arguments: dict[str, object], root: Path) -> ToolOutput:
    result = read_image.handle(arguments, ToolContext(workspace_root=root))
    assert isinstance(result, ToolOutput)
    return result


def test_read_image_attaches_supported_image(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "shot.png").write_bytes(_PNG)

    result = _run({"path": "docs/shot.png"}, tmp_path)

    assert not result.is_error
    assert result.result == {
        "path": "docs/shot.png",
        "mime_type": "image/png",
        "byte_count": len(_PNG),
    }
    assert len(result.attachments) == 1
    assert result.attachments[0].mime_type == "image/png"
    assert result.attachments[0].path == "docs/shot.png"


def test_read_image_detects_mime_from_content_not_extension(tmp_path: Path) -> None:
    (tmp_path / "image.bin").write_bytes(_PNG)

    result = _run({"path": "image.bin"}, tmp_path)

    assert not result.is_error
    assert result.attachments[0].mime_type == "image/png"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({}, "non-empty string"),
        ({"path": ""}, "non-empty string"),
        ({"path": "missing.png"}, "path not found"),
        ({"path": "."}, "path is not a file"),
        ({"path": "notes.txt"}, "unsupported image format"),
    ],
)
def test_read_image_reports_errors(
    tmp_path: Path, arguments: dict[str, object], message: str
) -> None:
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")

    result = _run(arguments, tmp_path)

    assert result.is_error
    assert result.attachments == []
    assert isinstance(result.result, dict)
    assert message in result.result["error"]


def test_read_image_reads_images_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(_PNG)

    result = _run({"path": str(outside)}, workspace)

    assert not result.is_error
    assert result.attachments[0].mime_type == "image/png"


def test_read_image_rejects_oversized_file_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = tmp_path / "big.png"
    with big.open("wb") as handle:
        handle.truncate(21 * 1024 * 1024)

    def fail_read(self: Path) -> bytes:
        raise AssertionError("read_bytes must not run for oversized images")

    monkeypatch.setattr(Path, "read_bytes", fail_read)

    result = _run({"path": "big.png"}, tmp_path)

    assert result.is_error
    assert isinstance(result.result, dict)
    assert "image too large" in result.result["error"]


def test_read_image_is_its_own_configurable_category() -> None:
    assert BUILTIN_TOOL_CATEGORIES["read-image"] == frozenset({"read_image"})
    assert "read" not in BUILTIN_TOOL_CATEGORIES


@pytest.mark.parametrize("alias", ["read", "read_image", "read-image"])
def test_read_image_group_aliases_enable_tool(alias: str) -> None:
    assert normalize_tool_categories((alias, "shell", "read-image")) == (
        "read-image",
        "shell",
    )
    excluded = effective_excluded_tool_names(
        Settings(provider="anthropic", allowed_tools=(alias,))
    )
    assert "read_image" not in excluded
    assert "shell" in excluded


def test_saved_profile_with_legacy_read_group_normalizes() -> None:
    profile = ModelProfileConfig(
        id="legacy",
        name="Legacy",
        provider_id="openai",
        allowed_tools=("read", "shell"),
    )

    profile.validate()

    assert profile.allowed_tools == ("read-image", "shell")


def test_command_with_legacy_read_group_normalizes() -> None:
    command = CommandConfig(
        id="review",
        name="review",
        slash_alias="/review",
        instructions="Review.",
        allowed_tools=("read", "ask_user"),
    )

    command.validate()

    assert command.allowed_tools == ("read-image", "ask-user")
