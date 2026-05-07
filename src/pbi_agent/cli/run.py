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
) -> int:
    from pbi_agent.agent.error_formatting import format_user_facing_error
    from pbi_agent.agent.session import run_single_turn
    from pbi_agent.display.console_display import ConsoleDisplay

    runtime = _coerce_runtime(settings)
    display = cast(
        DisplayProtocol,
        cast(Any, ConsoleDisplay)(verbose=runtime.settings.verbose),
    )

    try:
        outcome = run_single_turn(
            prompt,
            runtime,
            display,
            single_turn_hint=single_turn_hint,
            image_paths=image_paths,
            resume_session_id=resume_session_id,
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        _print_error(format_user_facing_error(exc))
        return 1

    if outcome.session_id:
        print(f"session_id={outcome.session_id}")
    return 4 if outcome.tool_errors else 0
