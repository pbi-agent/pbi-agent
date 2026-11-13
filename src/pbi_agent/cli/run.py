from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, cast

from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.display.protocol import DisplayProtocol

from .shared import _coerce_runtime, _print_error


def _handle_run_command(  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint
    args: argparse.Namespace,
    settings: Settings | ResolvedRuntime,
) -> int:
    runtime = _coerce_runtime(settings)
    project_dir = (Path.cwd() / args.project_dir).resolve()

    if not project_dir.exists():
        print(
            f"Error: Project directory does not exist: {project_dir}",
            file=sys.stderr,
        )
        return 1
    if not project_dir.is_dir():
        print(
            f"Error: Project path is not a directory: {project_dir}",
            file=sys.stderr,
        )
        return 1

    original_cwd = Path.cwd()
    try:
        os.chdir(project_dir)
        return _run_single_turn_command(
            prompt=args.prompt,
            settings=runtime,
            image_paths=list(args.images or []),
            resume_session_id=args.session_id,
            include_tool_history=bool(args.include_tool_history),
            show_steps=bool(getattr(args, "show_steps", False)),
        )
    finally:
        os.chdir(original_cwd)


def _run_single_turn_command(
    *,
    prompt: str,
    settings: Settings | ResolvedRuntime,
    single_turn_hint: str | None = None,
    image_paths: list[str] | None = None,
    resume_session_id: str | None = None,
    include_tool_history: bool = False,
    show_steps: bool = False,
) -> int:
    from pbi_agent.agent.error_formatting import format_user_facing_error
    from pbi_agent.agent.session import run_single_turn
    from pbi_agent.display.console_display import ConsoleDisplay
    from pbi_agent.web.session.headless import HeadlessSessionChannel

    runtime = _coerce_runtime(settings)
    console_display = cast(Any, ConsoleDisplay)(
        verbose=runtime.settings.verbose,
        final_response_only=not show_steps,
    )
    console = cast(DisplayProtocol, console_display)
    # CLI runs go through the same live-session channel as the web UI so the
    # saved session has the identical persisted timeline structure.
    channel = HeadlessSessionChannel(
        runtime,
        source="cli",
        session_id=resume_session_id,
        include_tool_history=include_tool_history,
        renderer=console,
    )

    title_job = _start_local_title_job(prompt, resume_session_id)
    try:
        outcome = channel.run(
            lambda display: run_single_turn(
                prompt,
                runtime,
                display,
                single_turn_hint=single_turn_hint,
                image_paths=image_paths,
                resume_session_id=resume_session_id,
                include_tool_history=include_tool_history,
            )
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        _print_error(format_user_facing_error(exc))
        return 1

    console_display.flush_final_response()
    if outcome.session_id and title_job is not None:
        _apply_local_title(outcome.session_id, prompt, title_job)
    if outcome.session_id:
        print(f"session_id={outcome.session_id}")
    return 4 if outcome.tool_errors else 0


class _LocalTitleJob:
    """Generate a local session title concurrently with the CLI turn."""

    def __init__(self, prompt: str) -> None:
        import threading

        self.title: str | None = None
        self._thread = threading.Thread(
            target=self._generate,
            args=(prompt,),
            daemon=True,
            name="pbi-agent-cli-session-title",
        )
        self._thread.start()

    def _generate(self, prompt: str) -> None:
        from pbi_agent import session_titles

        try:
            self.title = session_titles.generate_title(prompt)
        except Exception:
            self.title = None

    def result(self, timeout: float) -> str | None:
        self._thread.join(timeout)
        return self.title


def _start_local_title_job(
    prompt: str, resume_session_id: str | None
) -> _LocalTitleJob | None:
    from pbi_agent import session_titles

    if resume_session_id or prompt.lstrip().startswith("/"):
        return None
    if not session_titles.is_ready():
        return None
    return _LocalTitleJob(prompt)


def _apply_local_title(session_id: str, prompt: str, job: _LocalTitleJob) -> None:
    """Swap the truncated-prompt placeholder for the generated title, unless
    the session was renamed meanwhile."""
    from pbi_agent.session_store import SessionStore

    title = job.result(timeout=30.0)
    prefix = prompt.strip()[:80]
    if not title or title == prefix:
        return
    try:
        with SessionStore() as store:
            record = store.get_session(session_id)
            if record is None or not record.title.startswith(prefix):
                return
            store.replace_session_title(session_id, expected=record.title, title=title)
    except Exception:
        pass
