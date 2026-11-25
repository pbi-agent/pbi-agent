"""Background tasks for runs without a web live session.

Web chat sessions own a ``BackgroundTaskManager`` and deliver finished tasks
through their follow-up queue. Single-turn runs (``pbi-agent run``, board and
channel tasks) and sub-agents use ``RunBackgroundTasks`` instead: finished
results are injected at the next tool checkpoint, and when the model ends its
turn while tasks still run, the runtime waits for the next result and wakes
the model with it (bounded by ``MAX_BACKGROUND_WAKES``).
"""

from __future__ import annotations

import queue
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from pbi_agent.tools.background_tasks import (
    BackgroundTask,
    BackgroundTaskManager,
    render_background_result,
)

MAX_BACKGROUND_WAKES = 5
_MANAGER_ATTRIBUTE = "background_task_manager"
_POLL_SECONDS = 0.25


class RunBackgroundTasks:
    """Owns the background tasks started during one run."""

    def __init__(self) -> None:
        self._finished: queue.Queue[BackgroundTask] = queue.Queue()
        self.manager = BackgroundTaskManager(on_finished=self._finished.put)
        self.wakes = 0
        self._delivered: set[str] = set()

    def has_pending(self) -> bool:
        """Whether a task is running or finished without its result delivered."""
        return any(
            summary["status"] == "running" or summary["task_id"] not in self._delivered
            for summary in self.manager.list()
        )

    def drain_results(self) -> str | None:
        """Return rendered results of tasks that finished since the last call."""
        rendered: list[str] = []
        while True:
            try:
                task = self._finished.get_nowait()
            except queue.Empty:
                break
            self._delivered.add(task.task_id)
            rendered.append(render_background_result(task))
        return "\n\n".join(rendered) if rendered else None

    def wait_for_results(
        self,
        *,
        timeout_seconds: float | None = None,
        interrupted: Callable[[], bool] | None = None,
    ) -> str | None:
        """Block until a task finishes, then drain all results.

        Returns ``None`` on timeout, when ``interrupted()`` turns true, or when
        no task is running any more.
        """
        deadline = (
            None if timeout_seconds is None else time.monotonic() + timeout_seconds
        )
        while True:
            wait = _POLL_SECONDS
            if deadline is not None:
                wait = min(wait, deadline - time.monotonic())
                if wait <= 0:
                    return None
            try:
                task = self._finished.get(timeout=wait)
            except queue.Empty:
                if interrupted is not None and interrupted():
                    return None
                if not self.has_pending():
                    return None
                continue
            self._finished.put(task)
            return self.drain_results()

    def next_wake_input(
        self,
        *,
        deadline: float | None = None,
        interrupted: Callable[[], bool] | None = None,
    ) -> str | None:
        """Return results to wake the model with after it ended its turn.

        Finished results are returned immediately; otherwise this waits for a
        running task to finish. Returns ``None`` when nothing is pending, the
        wake budget is spent, ``interrupted()`` turns true, or ``deadline``
        (``time.monotonic()``) passes.
        """
        if self.wakes >= MAX_BACKGROUND_WAKES:
            return None
        text = self.drain_results()
        if text is None and self.has_pending():
            timeout = None
            if deadline is not None:
                timeout = max(0.0, deadline - time.monotonic())
            text = self.wait_for_results(
                timeout_seconds=timeout, interrupted=interrupted
            )
        if text is not None:
            self.wakes += 1
        return text

    def close(self) -> None:
        self.manager.close()


@contextmanager
def run_background_tasks(
    display: Any,
    *,
    own: bool = False,
) -> Iterator[RunBackgroundTasks | None]:
    """Give ``display`` a background task manager for the duration of a run.

    Yields ``None`` when the display already has one (a web live session
    delivers results itself) unless ``own`` is set (sub-agents keep their tasks
    and results to themselves). Running tasks are killed when the run exits.
    """
    if not own and getattr(display, _MANAGER_ATTRIBUTE, None) is not None:
        yield None
        return
    instance_attributes = getattr(display, "__dict__", {})
    had_own_attribute = _MANAGER_ATTRIBUTE in instance_attributes
    previous = instance_attributes.get(_MANAGER_ATTRIBUTE)
    background = RunBackgroundTasks()
    try:
        setattr(display, _MANAGER_ATTRIBUTE, background.manager)
    except AttributeError:
        background.close()
        yield None
        return
    try:
        yield background
    finally:
        background.close()
        try:
            if had_own_attribute:
                setattr(display, _MANAGER_ATTRIBUTE, previous)
            else:
                delattr(display, _MANAGER_ATTRIBUTE)
        except AttributeError:
            pass
