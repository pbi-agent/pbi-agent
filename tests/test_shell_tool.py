from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pbi_agent.tools import shell as shell_tool
from pbi_agent.tools.types import ToolContext


def test_shell_handle_runs_command_with_workspace_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_run(
        command: str,
        *,
        cwd: str,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        shell: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "shell": shell,
                "timeout": timeout,
                "env_has_path": "PATH" in env,
            }
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=b"stdout text",
            stderr=b"stderr text",
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    result = shell_tool.handle({"command": "echo hi"}, ToolContext())

    assert result == {
        "stdout": "stdout text",
        "stderr": "stderr text",
        "exit_code": 0,
    }
    assert calls == [
        {
            "command": "echo hi",
            "cwd": str(tmp_path.resolve()),
            "capture_output": True,
            "text": False,
            "shell": True,
            "timeout": shell_tool.MAX_TIMEOUT_MS / 1000.0,
            "env_has_path": True,
        }
    ]


def test_shell_handle_uses_requested_directory_and_clamps_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    workdir = tmp_path / "nested"
    workdir.mkdir()
    seen: dict[str, object] = {}

    def fake_run(
        command: str,
        *,
        cwd: str,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        shell: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        del env, capture_output, text, shell
        seen["command"] = command
        seen["cwd"] = cwd
        seen["timeout"] = timeout
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    shell_tool.handle(
        {
            "command": "pwd",
            "working_directory": "nested",
            "timeout_ms": shell_tool.MAX_TIMEOUT_MS * 2,
        },
        ToolContext(),
    )

    assert seen == {
        "command": "pwd",
        "cwd": str(workdir.resolve()),
        "timeout": shell_tool.MAX_TIMEOUT_MS / 1000.0,
    }


def test_shell_handle_returns_timeout_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        raise subprocess.TimeoutExpired(
            cmd="sleep 10",
            timeout=0.5,
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    result = shell_tool.handle(
        {"command": "sleep 10", "timeout_ms": 500},
        ToolContext(),
    )

    assert result == {
        "stdout": "partial stdout",
        "stderr": "partial stderr",
        "exit_code": None,
        "timed_out": True,
        "error": "Command timed out after 500ms.",
    }


def test_shell_handle_returns_error_payload_for_subprocess_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        raise OSError("boom")

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    result = shell_tool.handle({"command": "bad-command"}, ToolContext())

    assert result["stdout"] == ""
    assert result["stderr"] == "boom"
    assert result["exit_code"] == 1
    assert result["error"] == "Shell execution failed: boom"


def test_shell_handle_bounds_large_stdout_and_stderr(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    stdout = f"stdout-start-{'a' * (shell_tool.MAX_OUTPUT_CHARS + 50)}-stdout-end"
    stderr = f"stderr-start-{'b' * (shell_tool.MAX_OUTPUT_CHARS + 50)}-stderr-end"

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="python",
            returncode=0,
            stdout=stdout.encode("utf-8"),
            stderr=stderr.encode("utf-8"),
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    result = shell_tool.handle({"command": "python"}, ToolContext())

    assert result["exit_code"] == 0
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True
    assert len(result["stdout"]) <= shell_tool.MAX_OUTPUT_CHARS
    assert len(result["stderr"]) <= shell_tool.MAX_OUTPUT_CHARS
    assert result["stdout"].startswith("stdout-start-")
    assert result["stdout"].endswith("-stdout-end")
    assert result["stderr"].startswith("stderr-start-")
    assert result["stderr"].endswith("-stderr-end")
    assert "chars omitted" in result["stdout"]
    assert "chars omitted" in result["stderr"]


def test_resolve_working_directory_rejects_workspace_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent

    with pytest.raises(ValueError, match="outside workspace"):
        shell_tool._resolve_working_directory(tmp_path.resolve(), str(outside))
