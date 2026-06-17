from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from pbi_agent.tools import shell as shell_tool
from pbi_agent.tools.types import ToolContext


def _compression_result(text: str, **metadata: object) -> dict[str, object]:
    return {
        "compressed": text,
        **metadata,
    }


def _identity_compress(content: str) -> dict[str, object]:
    return _compression_result(content)


def test_compress_content_uses_headroom_local_compressor_config(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, **kwargs: object) -> None:
            calls["config"] = kwargs

    class FakeCompressor:
        def __init__(self, *, config: FakeConfig) -> None:
            calls["compressor_config"] = config

        def compress(self, content: str) -> dict[str, object]:
            calls["content"] = content
            return _compression_result(f"local {content}")

    def fake_import_module(name: str) -> object:
        calls["module"] = name
        return SimpleNamespace(
            UniversalCompressorConfig=FakeConfig,
            UniversalCompressor=FakeCompressor,
        )

    monkeypatch.setattr(shell_tool, "_HEADROOM_COMPRESS_CONTENT", None)
    monkeypatch.setattr(shell_tool, "import_module", fake_import_module)

    try:
        result = shell_tool._compress_content("content")
    finally:
        monkeypatch.setattr(shell_tool, "_HEADROOM_COMPRESS_CONTENT", None)

    assert result == _compression_result("local content")
    assert calls["module"] == "headroom.compression"
    assert calls["config"] == {"use_kompress": False, "ccr_enabled": False}
    assert isinstance(calls["compressor_config"], FakeConfig)
    assert calls["content"] == "content"


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
    compression_inputs: list[str] = []

    def fake_compress(content: str) -> dict[str, object]:
        compression_inputs.append(content)
        return _compression_result(content)

    monkeypatch.setattr(shell_tool, "_compress_content", fake_compress)

    result = shell_tool.handle({"command": "echo hi"}, ToolContext())

    assert result == {
        "stdout": "stdout text",
        "stderr": "stderr text",
        "exit_code": 0,
    }
    assert compression_inputs == ["stdout text", "stderr text"]
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
    monkeypatch.setattr(shell_tool, "_compress_content", _identity_compress)

    result = shell_tool.handle(
        {"command": "echo hi", "timeout_ms": 12_345},
        ToolContext(),
    )

    assert result["exit_code"] == 0
    assert seen == {"timeout": 12.345}


def test_shell_handle_can_disable_compression(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="command",
            returncode=0,
            stdout=b"raw stdout",
            stderr=b"raw stderr",
        )

    def fake_compress(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("compression=false should not call Headroom")

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "_compress_content", fake_compress)

    result = shell_tool.handle(
        {"command": "command", "compression": False},
        ToolContext(),
    )

    assert result == {
        "stdout": "raw stdout",
        "stderr": "raw stderr",
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


@pytest.mark.parametrize("compression", ["false", 0, 1])
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
    monkeypatch.setattr(shell_tool, "_compress_content", _identity_compress)

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
    monkeypatch.setattr(shell_tool, "_compress_content", _identity_compress)

    result = shell_tool.handle({"command": "python"}, ToolContext())

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


def test_shell_handle_compresses_stdout_and_stderr_independently(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="command",
            returncode=0,
            stdout=b"raw stdout",
            stderr=b"raw stderr",
        )

    calls: list[str] = []

    def fake_compress(content: str) -> dict[str, object]:
        calls.append(content)
        stream_name = "stdout" if content == "raw stdout" else "stderr"
        return _compression_result(
            f"compressed {stream_name}",
            tokens_saved=7,
            compression_ratio=0.5,
            tokens_before=20,
            tokens_after=13,
            savings_percentage=35.0,
            content_type="log",
            handler_used="LogCompressor",
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "_compress_content", fake_compress)

    result = shell_tool.handle({"command": "command"}, ToolContext())

    assert result["stdout"] == "compressed stdout"
    assert result["stderr"] == "compressed stderr"
    assert set(result) == {"stdout", "stderr", "exit_code"}
    assert calls == ["raw stdout", "raw stderr"]


def test_shell_handle_skips_compression_for_empty_streams(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="command", returncode=0, stdout=b"", stderr=b""
        )

    def fake_compress(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("empty shell streams should not be compressed")

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "_compress_content", fake_compress)

    result = shell_tool.handle({"command": "command"}, ToolContext())

    assert result == {"stdout": "", "stderr": "", "exit_code": 0}


def test_shell_handle_falls_back_when_compression_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="command",
            returncode=0,
            stdout=b"raw stdout",
            stderr=b"raw stderr",
        )

    def fake_compress(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("headroom boom")

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "_compress_content", fake_compress)

    result = shell_tool.handle({"command": "command"}, ToolContext())

    assert result == {
        "stdout": "raw stdout",
        "stderr": "raw stderr",
        "exit_code": 0,
    }


def test_shell_handle_bounds_compressed_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    compressed_stdout = "compressed-start-" + "x" * (shell_tool.MAX_STDOUT_CHARS + 100)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="command",
            returncode=0,
            stdout=b"raw stdout",
            stderr=b"",
        )

    def fake_compress(content: str) -> dict[str, object]:
        del content
        return _compression_result(compressed_stdout)

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "_compress_content", fake_compress)

    result = shell_tool.handle({"command": "command"}, ToolContext())

    assert result["stdout_truncated"] is True
    assert len(result["stdout"]) <= shell_tool.MAX_STDOUT_CHARS
    assert result["stdout"].startswith("compressed-start-")
    assert result["stderr"] == ""
    assert set(result) == {"stdout", "stderr", "stdout_truncated", "exit_code"}


def test_shell_timeout_payload_compresses_partial_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        raise subprocess.TimeoutExpired(
            cmd="sleep 10",
            timeout=0.5,
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

    def fake_compress(content: str) -> dict[str, object]:
        stream_name = "stdout" if content == "partial stdout" else "stderr"
        return _compression_result(f"compressed {stream_name}")

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "_compress_content", fake_compress)

    result = shell_tool.handle(
        {"command": "sleep 10", "timeout_ms": 500},
        ToolContext(),
    )

    assert result["stdout"] == "compressed stdout"
    assert result["stderr"] == "compressed stderr"
    assert result["timed_out"] is True
    assert result["error"] == "Command timed out after 500ms."


def test_shell_tool_schema_keeps_timeout_bounds_in_description_only() -> None:
    timeout_schema = shell_tool.SPEC.parameters_schema["properties"]["timeout_ms"]

    assert timeout_schema == {
        "type": "integer",
        "description": (
            "Timeout in milliseconds. Defaults to 30 000 (30 seconds), "
            "maximum 300 000 (5 minutes)."
        ),
    }


def test_shell_tool_schema_includes_compression_default_description() -> None:
    compression_schema = shell_tool.SPEC.parameters_schema["properties"]["compression"]

    assert compression_schema == {
        "type": "boolean",
        "description": (
            "Whether to compress stdout/stderr before returning them. "
            "Defaults to true. Set false when the full raw output is needed."
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
