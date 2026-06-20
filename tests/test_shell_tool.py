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
    monkeypatch.delenv(shell_tool.SHELL_BOOTSTRAP_ENV, raising=False)
    monkeypatch.delenv(shell_tool.SHELL_EXECUTABLE_ENV, raising=False)
    calls: list[dict[str, object]] = []

    def fake_run(
        command: str,
        *,
        cwd: str,
        capture_output: bool,
        text: bool,
        shell: bool,
        executable: str | None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "shell": shell,
                "executable": executable,
                "timeout": timeout,
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
            "executable": None,
            "timeout": shell_tool.DEFAULT_TIMEOUT_MS / 1000.0,
        }
    ]


def test_shell_handle_uses_requested_directory_and_clamps_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(shell_tool.SHELL_BOOTSTRAP_ENV, raising=False)
    monkeypatch.delenv(shell_tool.SHELL_EXECUTABLE_ENV, raising=False)
    workdir = tmp_path / "nested"
    workdir.mkdir()
    seen: dict[str, object] = {}

    def fake_run(
        command: str,
        *,
        cwd: str,
        capture_output: bool,
        text: bool,
        shell: bool,
        executable: str | None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        del capture_output, text, shell
        seen["command"] = command
        seen["cwd"] = cwd
        seen["executable"] = executable
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
        "executable": None,
        "timeout": shell_tool.MAX_TIMEOUT_MS / 1000.0,
    }


def test_shell_handle_honors_requested_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    seen: dict[str, object] = {}

    def fake_run(
        command: str,
        *,
        cwd: str,
        capture_output: bool,
        text: bool,
        shell: bool,
        executable: str | None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        del cwd, capture_output, text, shell, executable
        seen["timeout"] = timeout
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    result = shell_tool.handle(
        {"command": "echo hi", "timeout_ms": 12_345},
        ToolContext(),
    )

    assert result["exit_code"] == 0
    assert seen == {"timeout": 12.345}


def test_shell_handle_compresses_non_empty_streams_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[str, str]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="cmd",
            returncode=0,
            stdout=b"stdout text",
            stderr=b"stderr text",
        )

    def fake_compress_text(text: str, *, backend: str) -> str:
        calls.append((text, backend))
        return f"compressed: {text}"

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "compress_text", fake_compress_text)

    result = shell_tool.handle({"command": "cmd"}, ToolContext())

    assert result == {
        "stdout": "compressed: stdout text",
        "stderr": "compressed: stderr text",
        "exit_code": 0,
    }
    assert calls == [("stdout text", "auto"), ("stderr text", "auto")]


def test_shell_handle_skips_compression_when_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="cmd",
            returncode=0,
            stdout=b"stdout text",
            stderr=b"stderr text",
        )

    def fake_compress_text(text: str, *, backend: str) -> str:
        del text, backend
        raise AssertionError("compress_text should not be called")

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "compress_text", fake_compress_text)

    result = shell_tool.handle(
        {"command": "cmd", "compression": False},
        ToolContext(),
    )

    assert result == {
        "stdout": "stdout text",
        "stderr": "stderr text",
        "exit_code": 0,
    }


@pytest.mark.parametrize(
    "timeout_ms",
    ["1000", 1.5, True, False, 0, -1],
)
def test_shell_handle_rejects_invalid_timeout_without_running_subprocess(
    tmp_path: Path,
    monkeypatch,
    timeout_ms: object,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    result = shell_tool.handle(
        {"command": "echo hi", "timeout_ms": timeout_ms},
        ToolContext(),
    )

    assert result == {"error": "'timeout_ms' must be a positive integer."}


@pytest.mark.parametrize("compression", ["true", 1, 0, None, [], {}])
def test_shell_handle_rejects_invalid_compression_without_running_subprocess(
    tmp_path: Path,
    monkeypatch,
    compression: object,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    result = shell_tool.handle(
        {"command": "echo hi", "compression": compression},
        ToolContext(),
    )

    assert result == {"error": "'compression' must be a boolean."}


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


def test_shell_handle_compresses_timeout_partial_streams(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[str] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        raise subprocess.TimeoutExpired(
            cmd="sleep 10",
            timeout=0.5,
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

    def fake_compress_text(text: str, *, backend: str) -> str:
        assert backend == "auto"
        calls.append(text)
        return f"compressed: {text}"

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "compress_text", fake_compress_text)

    result = shell_tool.handle(
        {"command": "sleep 10", "timeout_ms": 500},
        ToolContext(),
    )

    assert result == {
        "stdout": "compressed: partial stdout",
        "stderr": "compressed: partial stderr",
        "exit_code": None,
        "timed_out": True,
        "error": "Command timed out after 500ms.",
    }
    assert calls == ["partial stdout", "partial stderr"]


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


def test_shell_handle_falls_back_to_decoded_output_when_compression_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="cmd",
            returncode=0,
            stdout=b"stdout text",
            stderr=b"stderr text",
        )

    def fake_compress_text(text: str, *, backend: str) -> str:
        del text, backend
        raise RuntimeError("compression failed")

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "compress_text", fake_compress_text)

    result = shell_tool.handle({"command": "cmd"}, ToolContext())

    assert result == {
        "stdout": "stdout text",
        "stderr": "stderr text",
        "exit_code": 0,
    }


def test_shell_handle_bounds_large_stdout_and_stderr_when_compression_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    stdout = f"stdout-start-{'a' * (shell_tool.MAX_STDOUT_CHARS + 50)}-stdout-end"
    stderr = f"stderr-start-{'b' * (shell_tool.MAX_STDERR_CHARS + 50)}-stderr-end"

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="python",
            returncode=0,
            stdout=stdout.encode("utf-8"),
            stderr=stderr.encode("utf-8"),
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    result = shell_tool.handle(
        {"command": "python", "compression": False},
        ToolContext(),
    )

    assert result["exit_code"] == 0
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True
    assert len(result["stdout"]) <= shell_tool.MAX_STDOUT_CHARS
    assert len(result["stderr"]) <= shell_tool.MAX_STDERR_CHARS
    assert result["stdout"].startswith("stdout-start-")
    assert result["stdout"].endswith("-stdout-end")
    assert result["stderr"].startswith("stderr-start-")
    assert result["stderr"].endswith("-stderr-end")
    assert "chars omitted" in result["stdout"]
    assert "chars omitted" in result["stderr"]


def test_shell_handle_bounds_output_after_compression(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="python",
            returncode=0,
            stdout=b"stdout raw",
            stderr=b"stderr raw",
        )

    def fake_compress_text(text: str, *, backend: str) -> str:
        assert backend == "auto"
        prefix = "stdout" if text.startswith("stdout") else "stderr"
        limit = (
            shell_tool.MAX_STDOUT_CHARS
            if prefix == "stdout"
            else shell_tool.MAX_STDERR_CHARS
        )
        return f"{prefix}-compressed-start-{'x' * (limit + 50)}-{prefix}-compressed-end"

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "compress_text", fake_compress_text)

    result = shell_tool.handle({"command": "python"}, ToolContext())

    assert result["exit_code"] == 0
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True
    assert len(result["stdout"]) <= shell_tool.MAX_STDOUT_CHARS
    assert len(result["stderr"]) <= shell_tool.MAX_STDERR_CHARS
    assert result["stdout"].startswith("stdout-compressed-start-")
    assert result["stdout"].endswith("-stdout-compressed-end")
    assert result["stderr"].startswith("stderr-compressed-start-")
    assert result["stderr"].endswith("-stderr-compressed-end")
    assert "chars omitted" in result["stdout"]
    assert "chars omitted" in result["stderr"]


def test_shell_tool_schema_keeps_timeout_bounds_in_description_only() -> None:
    timeout_schema = shell_tool.SPEC.parameters_schema["properties"]["timeout_ms"]

    assert timeout_schema == {
        "type": "integer",
        "description": (
            "Timeout in milliseconds. Defaults to 30 000 (30 seconds), "
            "maximum 300 000 (5 minutes)."
        ),
    }


def test_shell_tool_schema_exposes_optional_compression() -> None:
    schema = shell_tool.SPEC.parameters_schema

    assert schema["required"] == ["command"]
    assert schema["properties"]["compression"] == {
        "type": "boolean",
        "description": (
            "Whether to compress stdout/stderr before returning output. "
            "Defaults to true."
        ),
    }


def test_resolve_working_directory_allows_absolute_paths_outside_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()

    assert (
        shell_tool._resolve_working_directory(workspace.resolve(), str(outside))
        == outside.resolve()
    )
