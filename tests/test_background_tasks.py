from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pbi_agent.tools import background_task as background_task_tool
from pbi_agent.tools import raw_output
from pbi_agent.tools import shell as shell_tool
from pbi_agent.tools.background_tasks import (
    BackgroundTask,
    BackgroundTaskManager,
    render_background_result,
)
from pbi_agent.tools.types import ToolContext

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")


def _start(
    manager: BackgroundTaskManager, command: str, **kwargs: Any
) -> BackgroundTask:
    return manager.start(
        command,
        display_command=command,
        working_directory=".",
        shell_executable=None,
        timeout_ms=kwargs.get("timeout_ms", 10_000),
        compression=False,
        tool_call_id="call-1",
    )


def _collecting_manager(
    **kwargs: Any,
) -> tuple[BackgroundTaskManager, list[BackgroundTask], threading.Event]:
    finished: list[BackgroundTask] = []
    done = threading.Event()

    def on_finished(task: BackgroundTask) -> None:
        finished.append(task)
        done.set()

    return BackgroundTaskManager(on_finished=on_finished, **kwargs), finished, done


def test_completed_task_reports_output_and_exit_code() -> None:
    manager, finished, done = _collecting_manager()
    task = _start(manager, "echo out; echo err >&2; exit 3")
    assert done.wait(timeout=5)
    assert finished[0] is task
    assert task.status == "failed"
    assert task.exit_code == 3
    rendered = render_background_result(task)
    assert rendered == (
        f'<background_task_result task_id="{task.task_id}">\n'
        f"{task.task_id} exit 3 — echo out; echo err >&2; exit 3\n"
        "out\n"
        "[stderr]\n"
        "err\n"
        "</background_task_result>"
    )


def test_kill_marks_task_killed() -> None:
    manager, _finished, done = _collecting_manager()
    task = _start(manager, "sleep 30")
    manager.kill(task.task_id)
    assert done.wait(timeout=5)
    assert task.status == "killed"


def test_timeout_marks_task_timed_out() -> None:
    manager, _finished, done = _collecting_manager()
    task = _start(manager, "sleep 30", timeout_ms=200)
    assert done.wait(timeout=8)
    assert task.status == "timed_out"
    assert task.exit_code is None


def test_concurrency_limit_and_close_suppresses_callbacks() -> None:
    manager, finished, _done = _collecting_manager(max_concurrent=1)
    task = _start(manager, "sleep 30")
    with pytest.raises(RuntimeError, match="Too many"):
        _start(manager, "true")
    manager.close()
    assert task.process is not None
    task.process.wait(timeout=5)
    with pytest.raises(RuntimeError):
        _start(manager, "true")
    assert finished == []


def _context(tmp_path: Path, manager: Any, *, depth: int = 0) -> ToolContext:
    display = SimpleNamespace(
        background_task_manager=manager,
        interrupt_requested=lambda: False,
    )
    return ToolContext(
        display=display,  # type: ignore[arg-type]
        workspace_root=tmp_path,
        sub_agent_depth=depth,
        tool_call_id="call-1",
    )


def test_shell_run_in_background_returns_task_id(tmp_path: Path) -> None:
    manager, _finished, done = _collecting_manager()
    result = shell_tool.handle(
        {"intent": "Run test command", "command": "echo hi", "run_in_background": True},
        _context(tmp_path, manager),
    )
    assert result["background"] is True
    assert result["status"] == "running"
    assert done.wait(timeout=5)
    output = background_task_tool.handle(
        {"action": "output", "task_id": result["task_id"]},
        _context(tmp_path, manager),
    )
    assert output["stdout"].strip() == "hi"
    assert output["status"] == "completed"
    task = manager.get(result["task_id"])
    assert task is not None
    assert task.summary()["intent"] == "Run test command"
    assert f"{task.task_id} exit 0 — Run test command" in render_background_result(task)


def test_shell_background_allowed_for_sub_agents_and_rejected_when_unsupported(
    tmp_path: Path,
) -> None:
    manager, _finished, done = _collecting_manager()
    sub = shell_tool.handle(
        {"intent": "Run test command", "command": "true", "run_in_background": True},
        _context(tmp_path, manager, depth=1),
    )
    assert sub["status"] == "running"
    assert done.wait(timeout=5)
    unsupported = shell_tool.handle(
        {"intent": "Run test command", "command": "true", "run_in_background": True},
        _context(tmp_path, None),
    )
    assert "not supported" in unsupported["error"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            {
                "intent": "Run test command",
                "command": "true",
                "run_in_background": "yes",
            },
            "boolean",
        ),
        (
            {
                "intent": "Run test command",
                "command": "true",
                "run_in_background": True,
                "background_timeout_ms": 0,
            },
            "positive",
        ),
    ],
)
def test_shell_background_argument_validation(
    tmp_path: Path, arguments: dict[str, Any], message: str
) -> None:
    manager, _finished, _done = _collecting_manager()
    result = shell_tool.handle(arguments, _context(tmp_path, manager))
    assert message in result["error"]


def test_shell_has_no_background_management_fields() -> None:
    properties = shell_tool.SPEC.parameters_schema["properties"]
    assert "background_action" not in properties
    assert "task_id" not in properties


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({}, "'action'"),
        ({"action": "run"}, "'action'"),
        ({"action": "kill"}, "'task_id' is required"),
        ({"action": "status", "task_id": "  "}, "'task_id' is required"),
        ({"action": "output", "task_id": "bg-x"}, "Unknown"),
    ],
)
def test_background_task_argument_validation(
    tmp_path: Path, arguments: dict[str, Any], message: str
) -> None:
    manager, _finished, _done = _collecting_manager()
    result = background_task_tool.handle(arguments, _context(tmp_path, manager))
    assert message in result["error"]


def test_background_task_list_status_and_kill(tmp_path: Path) -> None:
    manager, _finished, done = _collecting_manager()
    context = _context(tmp_path, manager)
    assert background_task_tool.handle({"action": "list"}, context) == {"tasks": []}
    started = shell_tool.handle(
        {"intent": "Sleep", "command": "sleep 30", "run_in_background": True},
        context,
    )
    task_id = started["task_id"]
    listed = background_task_tool.handle({"action": "list"}, context)
    assert [task["task_id"] for task in listed["tasks"]] == [task_id]
    status = background_task_tool.handle(
        {"action": "status", "task_id": task_id}, context
    )
    assert status["status"] == "running"
    killed = background_task_tool.handle(
        {"action": "kill", "task_id": task_id}, context
    )
    assert killed["kill_requested"] is True
    assert done.wait(timeout=10)


def test_background_task_allowed_for_sub_agents_and_rejected_when_unsupported(
    tmp_path: Path,
) -> None:
    manager, _finished, _done = _collecting_manager()
    sub = background_task_tool.handle(
        {"action": "list"}, _context(tmp_path, manager, depth=1)
    )
    assert sub == {"tasks": []}
    unsupported = background_task_tool.handle(
        {"action": "list"}, _context(tmp_path, None)
    )
    assert "not supported" in unsupported["error"]


def test_cancellable_display_propagates_to_nested_sub_agents() -> None:
    import threading

    from pbi_agent.agent.session.runtime import _CancellableDisplay

    class _Inner:
        def interrupt_requested(self) -> bool:
            return False

        def begin_sub_agent(self, **_kwargs: object) -> _Inner:
            return _Inner()

    event = threading.Event()
    proxy = _CancellableDisplay(_Inner(), event)  # type: ignore[arg-type]
    nested = proxy.begin_sub_agent(task_instruction="x")
    grandchild = nested.begin_sub_agent(task_instruction="y")
    assert not nested.interrupt_requested()
    event.set()
    assert nested.interrupt_requested()
    assert grandchild.interrupt_requested()


def test_background_result_includes_raw_output_notice_when_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: raw_dir)
    manager, _finished, done = _collecting_manager()
    size = shell_tool.MAX_STDOUT_CHARS + 100
    task = _start(manager, f"{sys.executable} -c \"print('a' * {size})\"")
    assert done.wait(timeout=10)

    rendered = render_background_result(task)

    files = list(raw_dir.iterdir())
    assert len(files) == 1
    assert f"[truncated; full: {files[0]}]" in rendered
    assert rendered.count(str(files[0])) == 1
    assert "a" * size in files[0].read_text(encoding="utf-8")
    assert "middle dropped" not in rendered


def test_background_result_notes_partial_raw_output_when_middle_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pbi_agent.tools.stream_buffer import HEAD_MAX_CHARS, TAIL_MAX_CHARS

    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: tmp_path / "raw")
    manager, _finished, done = _collecting_manager()
    size = (HEAD_MAX_CHARS + TAIL_MAX_CHARS) * 2
    task = _start(manager, f"{sys.executable} -c \"print('a' * {size})\"")
    assert done.wait(timeout=10)

    rendered = render_background_result(task)

    assert task.stdout.dropped is True
    assert "middle dropped" in rendered


def test_background_result_without_truncation_creates_no_raw_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: raw_dir)
    manager, _finished, done = _collecting_manager()
    task = _start(manager, "echo hello")
    assert done.wait(timeout=5)

    rendered = render_background_result(task)

    assert "Output truncated" not in rendered
    assert not raw_dir.exists()


def _finished_task(status: str = "completed") -> BackgroundTask:
    return BackgroundTask(
        task_id="bg-test",
        command="cmd",
        working_directory=".",
        tool_call_id=None,
        timeout_ms=1000,
        compression=False,
        started_at=0.0,
        status=status,  # type: ignore[arg-type]
    )


def test_background_output_payload_reuses_raw_file_for_finished_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pbi_agent.tools.background_tasks import background_output_payload

    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: raw_dir)
    task = _finished_task()
    big = "a" * (shell_tool.MAX_STDOUT_CHARS + 1)

    first = background_output_payload(
        task,
        stdout=big,
        stderr="",
        stdout_dropped=False,
        stderr_dropped=False,
        compression=False,
    )
    second = background_output_payload(
        task,
        stdout=big,
        stderr="",
        stdout_dropped=False,
        stderr_dropped=False,
        compression=False,
    )

    assert first["raw_output_path"] == second["raw_output_path"]
    assert first["raw_output_path"] not in first["notice"]
    assert "raw_output_path" in first["notice"]
    assert len(list(raw_dir.iterdir())) == 1


def test_background_output_payload_writes_no_file_while_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pbi_agent.tools.background_tasks import background_output_payload

    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: raw_dir)

    payload = background_output_payload(
        _finished_task(status="running"),
        stdout="a" * (shell_tool.MAX_STDOUT_CHARS + 1),
        stderr="",
        stdout_dropped=False,
        stderr_dropped=False,
        compression=False,
    )

    assert payload["stdout_truncated"] is True
    assert "raw_output_path" not in payload
    assert "once the task finishes" in payload["notice"]
    assert not raw_dir.exists()


def test_background_output_payload_explains_dropped_middle_without_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pbi_agent.tools.background_tasks import (
        MIDDLE_DROPPED_NOTE,
        background_output_payload,
    )

    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: raw_dir)

    payload = background_output_payload(
        _finished_task(),
        stdout="short tail",
        stderr="",
        stdout_dropped=True,
        stderr_dropped=False,
        compression=False,
    )

    assert payload["stdout_middle_dropped"] is True
    assert "stdout_truncated" not in payload
    assert payload["notice"] == MIDDLE_DROPPED_NOTE
    assert not raw_dir.exists()


def test_background_task_output_action_separates_middle_dropped_from_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pbi_agent.tools.stream_buffer import HEAD_MAX_CHARS, TAIL_MAX_CHARS

    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: tmp_path / "raw")
    manager, _finished, done = _collecting_manager()
    size = (HEAD_MAX_CHARS + TAIL_MAX_CHARS) * 2
    task = _start(manager, f"{sys.executable} -c \"print('a' * {size})\"")
    assert done.wait(timeout=10)
    context = _context(tmp_path, manager)

    first = background_task_tool.handle(
        {"action": "output", "task_id": task.task_id}, context
    )
    second = background_task_tool.handle(
        {"action": "output", "task_id": task.task_id, "from_start": True}, context
    )

    assert first["stdout_middle_dropped"] is True
    assert first["stdout_truncated"] is True
    assert "the middle was dropped" in first["notice"]
    assert first["raw_output_path"] == second["raw_output_path"]
    assert first["raw_output_path"] not in first["notice"]


def test_foreground_shell_closes_stdin(tmp_path: Path) -> None:
    manager, _finished, _done = _collecting_manager()

    result = shell_tool.handle(
        {"intent": "Read stdin", "command": "read value; echo got:$value"},
        _context(tmp_path, manager),
    )

    assert result["exit_code"] == 0
    assert result["stdout"] == "got:\n"
    assert manager.list() == []


def test_foreground_shell_moves_running_command_to_background(tmp_path: Path) -> None:
    manager, finished, done = _collecting_manager()
    context = _context(tmp_path, manager)

    result = shell_tool.handle(
        {
            "intent": "Slow command",
            "command": "echo start; sleep 1; echo end",
            "yield_time_ms": 300,
        },
        context,
    )

    assert result["background"] is True
    assert result["status"] == "running"
    assert result["stdout"] == "start\n"
    assert done.wait(timeout=5)
    task = finished[0]
    assert task.task_id == result["task_id"]
    assert task.status == "completed"
    assert task.intent == "Slow command"
    rendered = render_background_result(task)
    assert f"{task.task_id} exit 0" in rendered
    assert "\nend\n[6 earlier chars already shown]\n" in rendered
    assert "start" not in rendered


def test_foreground_shell_kills_at_yield_without_background_manager(
    tmp_path: Path,
) -> None:
    context = ToolContext(
        display=SimpleNamespace(interrupt_requested=lambda: False),  # type: ignore[arg-type]
        workspace_root=tmp_path,
    )

    result = shell_tool.handle(
        {
            "intent": "Slow command",
            "command": "echo start; sleep 5",
            "yield_time_ms": 200,
        },
        context,
    )

    assert result["timed_out"] is True
    assert result["stdout"] == "start\n"
    assert result["error"] == (
        "Command killed after 200ms; background tasks are not available here."
    )


def test_foreground_shell_kills_at_yield_when_background_is_full(
    tmp_path: Path,
) -> None:
    manager, _finished, _done = _collecting_manager(max_concurrent=1)
    _start(manager, "sleep 30")
    try:
        result = shell_tool.handle(
            {"intent": "Slow command", "command": "sleep 5", "yield_time_ms": 200},
            _context(tmp_path, manager),
        )
    finally:
        manager.close()

    assert result["timed_out"] is True


def test_background_task_output_returns_only_new_output(tmp_path: Path) -> None:
    manager, _finished, done = _collecting_manager()
    context = _context(tmp_path, manager)
    task = _start(manager, "echo one; sleep 0.4; echo two")

    first = None
    for _ in range(40):
        first = background_task_tool.handle(
            {"action": "output", "task_id": task.task_id}, context
        )
        if first["stdout"]:
            break
        threading.Event().wait(0.05)
    assert first is not None and first["stdout"] == "one\n"
    assert done.wait(timeout=5)
    second = background_task_tool.handle(
        {"action": "output", "task_id": task.task_id}, context
    )
    again = background_task_tool.handle(
        {"action": "output", "task_id": task.task_id, "from_start": True}, context
    )

    assert second["stdout"] == "two\n"
    assert second["earlier_chars"] == 4
    assert again["stdout"] == "one\ntwo\n"


def test_background_task_input_requires_tty(tmp_path: Path) -> None:
    manager, _finished, _done = _collecting_manager()
    context = _context(tmp_path, manager)
    task = _start(manager, "sleep 30")
    try:
        result = background_task_tool.handle(
            {"action": "input", "task_id": task.task_id, "chars": "x"}, context
        )
    finally:
        manager.close()

    assert "start the command with 'tty': true" in result["error"]


def test_tty_task_accepts_input_and_ctrl_c(tmp_path: Path) -> None:
    manager, _finished, done = _collecting_manager()
    context = _context(tmp_path, manager)
    started = shell_tool.handle(
        {
            "intent": "Python REPL",
            "command": f"{sys.executable} -q -i",
            "tty": True,
            "yield_time_ms": 500,
        },
        context,
    )
    task_id = started["task_id"]
    try:
        answer = background_task_tool.handle(
            {"action": "input", "task_id": task_id, "chars": "6*7\n", "wait_ms": 5000},
            context,
        )
        background_task_tool.handle(
            {
                "action": "input",
                "task_id": task_id,
                "chars": "import time; time.sleep(30)\n",
                "wait_ms": 200,
            },
            context,
        )
        interrupted = background_task_tool.handle(
            {"action": "input", "task_id": task_id, "chars": "\u0003", "wait_ms": 5000},
            context,
        )
        background_task_tool.handle(
            {"action": "input", "task_id": task_id, "chars": "\u0004", "wait_ms": 0},
            context,
        )
        assert done.wait(timeout=5)
    finally:
        manager.close()

    assert "42" in answer["stdout"]
    assert "\x1b" not in answer["stdout"]
    assert "KeyboardInterrupt" in interrupted["stdout"]


def test_foreground_shell_without_handoff_kills_at_yield(tmp_path: Path) -> None:
    manager, _finished, _done = _collecting_manager()
    context = _context(tmp_path, manager)
    context.background_handoff = False

    result = shell_tool.handle(
        {"intent": "User command", "command": "sleep 5", "yield_time_ms": 200},
        context,
    )

    assert result["timed_out"] is True
    assert manager.list() == []
