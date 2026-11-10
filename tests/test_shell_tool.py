from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pbi_agent.tools import raw_output
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
        check: bool,
        capture_output: bool,
        text: bool,
        shell: bool,
        executable: str | None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(
            {
                "intent": "Run test command",
                "command": command,
                "cwd": cwd,
                "check": check,
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

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "echo hi"}, ToolContext()
    )

    assert result == {
        "stdout": "stdout text",
        "stderr": "stderr text",
        "exit_code": 0,
    }
    assert calls == [
        {
            "intent": "Run test command",
            "command": "echo hi",
            "cwd": str(tmp_path.resolve()),
            "check": False,
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
        check: bool,
        capture_output: bool,
        text: bool,
        shell: bool,
        executable: str | None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        del check, capture_output, text, shell
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
            "intent": "Run test command",
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
        check: bool,
        capture_output: bool,
        text: bool,
        shell: bool,
        executable: str | None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        del cwd, check, capture_output, text, shell, executable
        seen["timeout"] = timeout
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "echo hi", "timeout_ms": 12_345},
        ToolContext(),
    )

    assert result["exit_code"] == 0
    assert seen == {"timeout": 12.345}


def test_shell_handle_interrupts_running_process_from_display(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    interrupted = threading.Event()
    display = SimpleNamespace(interrupt_requested=interrupted.is_set)
    script = "import time; time.sleep(30)"
    command = (
        subprocess.list2cmdline([sys.executable, "-c", script])
        if os.name == "nt"
        else f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    )
    timer = threading.Timer(0.2, interrupted.set)

    started_at = time.monotonic()
    timer.start()
    try:
        result = shell_tool.handle(
            {
                "intent": "Run test command",
                "command": command,
                "compression": False,
                "timeout_ms": 10_000,
            },
            ToolContext(display=cast(Any, display)),
        )
    finally:
        timer.cancel()

    assert time.monotonic() - started_at < 5
    assert result == {
        "stdout": "",
        "stderr": "",
        "exit_code": 130,
        "interrupted": True,
        "error": "Command interrupted by user.",
    }


def test_shell_handle_interrupts_only_targeted_tool_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    interrupted_call_ids: set[str] = set()
    display = SimpleNamespace(
        interrupt_requested=lambda: False,
        tool_interrupt_requested=lambda call_id: call_id in interrupted_call_ids,
    )
    script = "import time; time.sleep(30)"
    command = (
        subprocess.list2cmdline([sys.executable, "-c", script])
        if os.name == "nt"
        else f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    )
    timer = threading.Timer(0.2, interrupted_call_ids.add, args=("call-shell",))

    started_at = time.monotonic()
    timer.start()
    try:
        result = shell_tool.handle(
            {
                "intent": "Run test command",
                "command": command,
                "compression": False,
                "timeout_ms": 10_000,
            },
            ToolContext(
                display=cast(Any, display),
                tool_call_id="call-shell",
            ),
        )
    finally:
        timer.cancel()

    assert time.monotonic() - started_at < 5
    assert result["exit_code"] == 130
    assert result["interrupted"] is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group behavior")
def test_shell_handle_interrupts_descendant_after_shell_leader_exits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    interrupted = threading.Event()
    display = SimpleNamespace(interrupt_requested=interrupted.is_set)
    timer = threading.Timer(0.2, interrupted.set)

    started_at = time.monotonic()
    timer.start()
    try:
        result = shell_tool.handle(
            {
                "intent": "Run test command",
                "command": "sleep 30 &",
                "compression": False,
                "timeout_ms": 10_000,
            },
            ToolContext(display=cast(Any, display)),
        )
    finally:
        timer.cancel()

    assert time.monotonic() - started_at < 5
    assert result["exit_code"] == 130
    assert result["interrupted"] is True


def test_shell_handle_stops_process_before_propagating_keyboard_interrupt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    display = SimpleNamespace(interrupt_requested=lambda: False)

    def interrupt_communication(**_kwargs: object) -> tuple[bytes, bytes]:
        raise KeyboardInterrupt

    class FakePopen:
        pid = 123
        returncode = None

        @classmethod
        def __class_getitem__(cls, _item: object) -> type[FakePopen]:
            return cls

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        communicate = staticmethod(interrupt_communication)

    stopped: list[object] = []
    monkeypatch.setattr(shell_tool.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(
        shell_tool,
        "_stop_process",
        lambda active_process: stopped.append(active_process) or (b"", b""),
    )

    with pytest.raises(KeyboardInterrupt):
        shell_tool.handle(
            {"intent": "Run test command", "command": "long-running"},
            ToolContext(display=cast(Any, display)),
        )

    assert len(stopped) == 1
    assert isinstance(stopped[0], FakePopen)


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
        # Whitespace-only rewrite: compression applied but nothing lost.
        return f"{text}   \n\n\n"

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "compress_text", fake_compress_text)

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "cmd"}, ToolContext()
    )

    assert result == {
        "stdout": "stdout text   \n\n\n",
        "stderr": "stderr text   \n\n\n",
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
        {"intent": "Run test command", "command": "cmd", "compression": False},
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
        {"intent": "Run test command", "command": "echo hi", "timeout_ms": timeout_ms},
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
        {
            "intent": "Run test command",
            "command": "echo hi",
            "compression": compression,
        },
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
        {"intent": "Run test command", "command": "sleep 10", "timeout_ms": 500},
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
        return f"{text}\n"

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_tool, "compress_text", fake_compress_text)

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "sleep 10", "timeout_ms": 500},
        ToolContext(),
    )

    assert result == {
        "stdout": "partial stdout\n",
        "stderr": "partial stderr\n",
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

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "bad-command"}, ToolContext()
    )

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

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "cmd"}, ToolContext()
    )

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
        {"intent": "Run test command", "command": "python", "compression": False},
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

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "python"}, ToolContext()
    )

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

    assert schema["required"] == ["intent", "command"]
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


@pytest.mark.parametrize("intent", [None, "", "   ", 3])
def test_shell_handle_requires_intent(intent: object) -> None:
    arguments: dict[str, object] = {"command": "echo hi"}
    if intent is not None:
        arguments["intent"] = intent

    result = shell_tool.handle(arguments, ToolContext())

    assert "'intent'" in result["error"]


def _fake_completed_run(
    monkeypatch: pytest.MonkeyPatch, *, stdout: str, stderr: str
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="cmd",
            returncode=0,
            stdout=stdout.encode("utf-8"),
            stderr=stderr.encode("utf-8"),
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)


@pytest.fixture
def raw_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw_dir = tmp_path / "raw-output"
    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: raw_dir)
    return raw_dir


@pytest.mark.parametrize("compression", [True, False])
def test_shell_truncated_output_saves_raw_file_with_notice(
    raw_output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    compression: bool,
) -> None:
    stdout = f"out-start-{'a' * (shell_tool.MAX_STDOUT_CHARS * 2)}-out-end"
    stderr = "small stderr"
    _fake_completed_run(monkeypatch, stdout=stdout, stderr=stderr)
    # Whitespace-only compression: only truncation should be reported.
    monkeypatch.setattr(
        shell_tool, "compress_text", lambda text, *, backend: f"{text}\n\n"
    )

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "cmd", "compression": compression},
        ToolContext(),
    )

    assert result["stdout_truncated"] is True
    raw_path = Path(result["raw_output_path"])
    assert raw_path.parent == raw_output_dir
    assert raw_path.name.startswith(raw_output.RAW_OUTPUT_PREFIX)
    assert str(raw_path) in result["notice"]
    assert result["notice"].startswith("Output truncated.")
    content = raw_path.read_text(encoding="utf-8")
    # The file holds the original, uncompressed, unbounded output.
    assert content == (f"===== stdout =====\n{stdout}\n===== stderr =====\n{stderr}\n")
    assert "stdout_compressed" not in result
    if os.name != "nt":
        assert raw_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("compression", [True, False])
def test_shell_untruncated_output_creates_no_raw_file(
    raw_output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    compression: bool,
) -> None:
    _fake_completed_run(monkeypatch, stdout="short out", stderr="short err")
    monkeypatch.setattr(shell_tool, "compress_text", lambda text, *, backend: text)

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "cmd", "compression": compression},
        ToolContext(),
    )

    assert "raw_output_path" not in result
    assert "notice" not in result
    assert not raw_output_dir.exists()


def test_shell_compression_truncation_saves_raw_file(
    raw_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_completed_run(monkeypatch, stdout="raw stdout", stderr="raw stderr")
    monkeypatch.setattr(
        shell_tool,
        "compress_text",
        lambda text, *, backend: "x" * (shell_tool.MAX_STDERR_CHARS + 1),
    )

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "cmd"}, ToolContext()
    )

    assert result["stderr_truncated"] is True
    content = Path(result["raw_output_path"]).read_text(encoding="utf-8")
    assert "raw stdout" in content and "raw stderr" in content


def test_shell_raw_output_files_are_unique_per_execution(
    raw_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_completed_run(
        monkeypatch, stdout="a" * (shell_tool.MAX_STDOUT_CHARS + 1), stderr=""
    )
    args = {"intent": "Run test command", "command": "cmd", "compression": False}

    first = shell_tool.handle(args, ToolContext())
    second = shell_tool.handle(args, ToolContext())

    assert first["raw_output_path"] != second["raw_output_path"]
    assert len(list(raw_output_dir.iterdir())) == 2


def test_shell_raw_output_write_failure_omits_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: blocker / "raw")
    _fake_completed_run(
        monkeypatch, stdout="a" * (shell_tool.MAX_STDOUT_CHARS + 1), stderr=""
    )

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "cmd", "compression": False},
        ToolContext(),
    )

    assert result["stdout_truncated"] is True
    assert "raw_output_path" not in result
    assert "notice" not in result


def test_shell_lossy_compression_without_truncation_saves_raw_file(
    raw_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_stdout = "collected 3 items\ntest_a PASSED\ntest_b PASSED\ntest_c PASSED\n"
    _fake_completed_run(monkeypatch, stdout=raw_stdout, stderr="warn\n")
    monkeypatch.setattr(
        shell_tool,
        "compress_text",
        lambda text, *, backend: (
            "test output: pytest success\n" if text.startswith("collected") else text
        ),
    )

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "cmd"}, ToolContext()
    )

    assert result["stdout"] == "test output: pytest success\n"
    assert result["stdout_compressed"] is True
    assert "stderr_compressed" not in result
    assert "stdout_truncated" not in result
    assert result["notice"].startswith(
        "Output compressed (some content summarized or omitted)."
    )
    assert "truncated" not in result["notice"]
    content = Path(result["raw_output_path"]).read_text(encoding="utf-8")
    assert content == (
        f"===== stdout =====\n{raw_stdout}\n===== stderr =====\nwarn\n\n"
    )


def test_shell_lossy_compression_and_truncation_notice(
    raw_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_completed_run(monkeypatch, stdout="raw", stderr="")
    monkeypatch.setattr(
        shell_tool,
        "compress_text",
        lambda text, *, backend: "y" * (shell_tool.MAX_STDOUT_CHARS + 1),
    )

    result = shell_tool.handle(
        {"intent": "Run test command", "command": "cmd"}, ToolContext()
    )

    assert result["stdout_compressed"] is True
    assert result["stdout_truncated"] is True
    assert result["notice"].startswith(
        "Output compressed (some content summarized or omitted) and truncated."
    )


@pytest.mark.parametrize(
    ("raw", "compressed", "lossy"),
    [
        ("a\nb\n", "a\nb\n", False),
        ("a\n\n\n\nb\n", "a\n\nb\n", False),
        ("x   \ny\t\n", "x\ny\n", False),
        ("\x1b[31mred\x1b[0m\n", "red\n", False),
        ("line\r\nnext\r\n", "line\nnext\n", False),
        ("    indented\n", "indented\n", False),
        ("col1     col2\tcol3\n", "col1 col2 col3\n", False),
        ("a\na\na\n", "a\n", True),
        ("collected 2 items\n..\n2 passed\n", "test output: pytest success\n", True),
        ("payload <html>...</html>\n", "[opaque payload omitted: kind=html]\n", True),
    ],
)
def test_is_lossy_compression_ignores_cosmetic_changes(
    raw: str, compressed: str, lossy: bool
) -> None:
    assert shell_tool._is_lossy_compression(raw, compressed) is lossy


def test_cosmetic_compression_with_real_backend_creates_no_raw_file(
    raw_output_dir: Path,
) -> None:
    # Call the payload builder directly: faking ``subprocess.run`` would also
    # intercept codetool-shell's Rust backend subprocess.
    result = shell_tool._build_output_payload(
        stdout="a\n\n\n\nb   \n", stderr="", compression=True
    )

    assert "stdout_compressed" not in result
    assert "notice" not in result
    assert not raw_output_dir.exists()


def test_test_runner_summary_with_real_backend_saves_raw_file(
    raw_output_dir: Path,
) -> None:
    raw_stdout = (
        "============ test session starts ============\n"
        "platform linux\ncollected 200 items\n\n"
        f"tests/test_a.py {'.' * 200} [100%]\n\n"
        "============ 200 passed in 1.2s ============\n"
    )

    result = shell_tool._build_output_payload(
        stdout=raw_stdout, stderr="", compression=True
    )

    assert result["stdout"] != raw_stdout
    assert result["stdout_compressed"] is True
    assert "stdout_truncated" not in result
    assert result["notice"].startswith("Output compressed")
    assert raw_stdout in Path(result["raw_output_path"]).read_text(encoding="utf-8")
