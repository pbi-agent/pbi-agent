from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pbi_agent.tools import background_task as background_task_tool
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
    assert f'task_id="{task.task_id}" status="failed" exit_code="3"' in rendered
    assert "out" in rendered and "err" in rendered


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
    assert "intent: Run test command" in render_background_result(task)


def test_shell_background_rejected_for_sub_agents_and_unsupported(
    tmp_path: Path,
) -> None:
    manager, _finished, _done = _collecting_manager()
    sub = shell_tool.handle(
        {"intent": "Run test command", "command": "true", "run_in_background": True},
        _context(tmp_path, manager, depth=1),
    )
    assert "sub-agents" in sub["error"]
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


def test_background_task_rejected_for_sub_agents_and_unsupported(
    tmp_path: Path,
) -> None:
    manager, _finished, _done = _collecting_manager()
    sub = background_task_tool.handle(
        {"action": "list"}, _context(tmp_path, manager, depth=1)
    )
    assert "sub-agents" in sub["error"]
    unsupported = background_task_tool.handle(
        {"action": "list"}, _context(tmp_path, None)
    )
    assert "not supported" in unsupported["error"]


def test_stream_tail_keeps_tail_of_oversized_chunk() -> None:
    from pbi_agent.tools.background_tasks import TAIL_MAX_CHARS, _StreamTail

    tail = _StreamTail()
    tail.append("a" * 10 + "b" * TAIL_MAX_CHARS)
    assert tail.text() == "b" * TAIL_MAX_CHARS
    assert tail.dropped is True


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
