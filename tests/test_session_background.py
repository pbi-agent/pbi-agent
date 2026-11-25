from __future__ import annotations

import sys
import time
from types import SimpleNamespace

import pytest

from pbi_agent.agent.session import background as background_module
from pbi_agent.agent.session.background import (
    RunBackgroundTasks,
    run_background_tasks,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")


def _start(background: RunBackgroundTasks, command: str) -> str:
    task = background.manager.start(
        command,
        display_command=command,
        intent="",
        working_directory=".",
        shell_executable=None,
        timeout_ms=10_000,
        compression=False,
        tool_call_id=None,
    )
    return task.task_id


def test_next_wake_input_waits_for_running_task() -> None:
    background = RunBackgroundTasks()
    try:
        task_id = _start(background, "sleep 0.2; echo hi")
        assert background.drain_results() is None

        text = background.next_wake_input()

        assert text is not None
        assert f'task_id="{task_id}"' in text
        assert "hi" in text
        assert background.wakes == 1
        assert background.next_wake_input() is None
    finally:
        background.close()


def test_next_wake_input_respects_wake_cap(monkeypatch) -> None:
    monkeypatch.setattr(background_module, "MAX_BACKGROUND_WAKES", 1)
    background = RunBackgroundTasks()
    try:
        _start(background, "true")
        assert background.next_wake_input() is not None
        _start(background, "true")
        assert background.next_wake_input() is None
    finally:
        background.close()


def test_next_wake_input_stops_on_interrupt_and_deadline() -> None:
    background = RunBackgroundTasks()
    try:
        _start(background, "sleep 30")
        started = time.monotonic()
        assert background.next_wake_input(interrupted=lambda: True) is None
        assert background.next_wake_input(deadline=time.monotonic() + 0.2) is None
        assert time.monotonic() - started < 5
        assert background.wakes == 0
    finally:
        background.close()


def test_run_background_tasks_installs_and_removes_manager() -> None:
    display = SimpleNamespace()
    with run_background_tasks(display) as background:
        assert background is not None
        assert display.background_task_manager is background.manager
        task_id = _start(background, "sleep 30")
    assert not hasattr(display, "background_task_manager")
    task = background.manager.get(task_id)
    assert task is not None and task.process is not None
    task.process.wait(timeout=5)
    for _ in range(50):
        if task.status != "running":
            break
        time.sleep(0.05)
    assert task.status == "killed"


def test_run_background_tasks_defers_to_existing_manager_unless_owned() -> None:
    existing = object()
    display = SimpleNamespace(background_task_manager=existing)

    with run_background_tasks(display) as shared:
        assert shared is None
        assert display.background_task_manager is existing

    with run_background_tasks(display, own=True) as owned:
        assert owned is not None
        assert display.background_task_manager is owned.manager
    assert display.background_task_manager is existing


def test_wake_raises_when_interrupted_during_the_wait() -> None:
    from pbi_agent.agent.session import runtime as runtime_module
    from pbi_agent.agent.session.shared import SessionTurnInterrupted

    background = SimpleNamespace(next_wake_input=lambda **_kwargs: None)
    display = SimpleNamespace(interrupt_requested=lambda: True)

    with pytest.raises(SessionTurnInterrupted):
        runtime_module._wake_on_background_results(
            background=background,  # pyright: ignore[reportArgumentType]
            provider=SimpleNamespace(),
            response=SimpleNamespace(),  # pyright: ignore[reportArgumentType]
            display=display,  # pyright: ignore[reportArgumentType]
            session_usage=SimpleNamespace(),  # pyright: ignore[reportArgumentType]
            turn_usage=SimpleNamespace(),  # pyright: ignore[reportArgumentType]
            tracer=None,
        )
