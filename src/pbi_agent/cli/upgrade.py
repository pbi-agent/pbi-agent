from __future__ import annotations

import argparse
import subprocess
import sys

from pbi_agent import __version__
from pbi_agent.self_update import (
    UpdateCheckError,
    detect_upgrade_plan,
    installed_version,
    is_newer_version,
    latest_pypi_version,
    update_available_message,
    windows_deferred_command,
)

from .shared import _print_error

UPGRADE_COMMANDS = frozenset({"upgrade", "update"})
EXIT_ERROR = 1
# Same convention as `dnf check-update`: 100 means an update is available.
EXIT_UPDATE_AVAILABLE = 100


def _handle_upgrade_command(args: argparse.Namespace) -> int:  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint
    try:
        latest = latest_pypi_version()
    except UpdateCheckError as exc:
        _print_error(f"unable to check PyPI for the latest pbi-agent version: {exc}")
        return EXIT_ERROR

    if not is_newer_version(latest, __version__):
        print(f"pbi-agent {__version__} is up to date (latest: {latest}).")
        return 0

    print(update_available_message(__version__, latest))
    plan = detect_upgrade_plan()
    if args.check:
        print(plan.hint)
        return EXIT_UPDATE_AVAILABLE

    if plan.command is None:
        _print_error(f"{plan.problem}\n{plan.manual_hint}")
        return EXIT_ERROR

    if sys.platform == "win32":
        return _start_deferred_windows_upgrade(
            plan.installer, plan.command, plan.manual_hint
        )
    return _run_upgrade(plan.installer, plan.command, plan.manual_hint)


def _run_upgrade(installer: str, command: tuple[str, ...], manual_hint: str) -> int:
    print(f"Upgrading with {installer}: {' '.join(command)}", flush=True)
    try:
        completed = subprocess.run(command, check=False)
    except OSError as exc:
        _print_error(f"failed to run {installer}: {exc}\n{manual_hint}")
        return EXIT_ERROR
    if completed.returncode != 0:
        _print_error(
            f"upgrade failed (exit code {completed.returncode}).\n{manual_hint}"
        )
        return completed.returncode

    current = installed_version()
    if current is None or not is_newer_version(current, __version__):
        _print_error(
            f"{installer} finished, but pbi-agent is still {current or __version__}.\n"
            "A version constraint in the original install may be pinning it; "
            "reinstall without the constraint."
        )
        return EXIT_ERROR
    print(f"pbi-agent upgraded to {current}.")
    return 0


def _start_deferred_windows_upgrade(
    installer: str, command: tuple[str, ...], manual_hint: str
) -> int:
    # Windows locks the running launcher, interpreter, and extension DLLs, so the
    # installer has to run after this process exits.
    try:
        subprocess.Popen(windows_deferred_command(command))
    except OSError as exc:
        _print_error(f"failed to start the upgrade: {exc}\n{manual_hint}")
        return EXIT_ERROR
    print(f"Upgrading with {installer} after pbi-agent exits: {' '.join(command)}")
    return 0
