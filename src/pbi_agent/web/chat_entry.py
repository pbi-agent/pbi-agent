from __future__ import annotations

import argparse
import os
import threading
import time

from pbi_agent.cli import main


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="pbi-agent web console entrypoint")
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def _start_parent_watchdog(parent_pid: int) -> None:
    threading.Thread(
        target=_watch_parent_process,
        args=(parent_pid,),
        name="pbi-agent-parent-watchdog",
        daemon=True,
    ).start()


def _watch_parent_process(parent_pid: int) -> None:
    if parent_pid <= 0:
        return
    if os.name == "nt":
        _watch_parent_process_windows(parent_pid)
        return

    while True:
        if not _parent_process_exists(parent_pid):
            os._exit(0)
        time.sleep(0.5)


def _parent_process_exists(parent_pid: int) -> bool:
    try:
        os.kill(parent_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _watch_parent_process_windows(parent_pid: int) -> None:
    import ctypes

    kernel32 = ctypes.windll.kernel32
    synchronize = 0x00100000
    infinite = 0xFFFFFFFF
    wait_object_0 = 0x00000000

    handle = kernel32.OpenProcess(synchronize, False, parent_pid)
    if not handle:
        os._exit(0)

    try:
        result = kernel32.WaitForSingleObject(handle, infinite)
        if result == wait_object_0:
            os._exit(0)
    finally:
        kernel32.CloseHandle(handle)


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _start_parent_watchdog(args.parent_pid)

    cli_argv: list[str] = []
    if args.verbose:
        cli_argv.append("--verbose")
    cli_argv.append("console")
    return main(cli_argv)


if __name__ == "__main__":
    raise SystemExit(run())
