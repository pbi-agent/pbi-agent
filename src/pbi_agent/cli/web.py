from __future__ import annotations

import argparse
import contextlib
import dataclasses
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.web.defaults import DEFAULT_WEB_PORT
from pbi_agent.workspace_context import current_workspace_context

from .shared import (
    WEB_MANAGER_LEASE_STALE_SECONDS,
    WEB_SERVER_BROWSER_CONNECT_TIMEOUT_SECONDS,
    WEB_SERVER_BROWSER_POLL_INTERVAL_SECONDS,
    WEB_SERVER_BROWSER_WAIT_RETRY_SECONDS,
    WEB_SERVER_BROWSER_WAIT_TIMEOUT_SECONDS,
    _coerce_runtime,
)

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class WebServerWaitResult:
    ready: bool
    connect_host: str
    port: int
    timeout_seconds: float
    elapsed_seconds: float
    attempts: int
    last_error: str | None = None

    def __bool__(self) -> bool:
        return self.ready


def _handle_web_command(
    args: argparse.Namespace,
    settings: Settings | ResolvedRuntime,
) -> int:
    runtime = _coerce_runtime(settings)
    if args.port < 1 or args.port > 65535:
        print("Error: --port must be between 1 and 65535.", file=sys.stderr)
        return 2

    try:
        if _current_workspace_has_active_web_manager():
            print(
                "Error: another web app instance is already managing this workspace.",
                file=sys.stderr,
            )
            return 1
    except Exception as exc:
        print(f"Error: unable to inspect web server lease: {exc}", file=sys.stderr)
        return 1

    if not _resolve_web_command_port(args):
        return 1

    browser_url = _browser_target_url(args)
    print(f"Serving web UI on {browser_url}")
    if not getattr(args, "no_open", False):
        _start_browser_open_thread(args.host, args.port, browser_url)

    server = _create_web_server(
        args,
        runtime,
    )
    try:
        server.serve(debug=args.dev)
        return 0
    except KeyboardInterrupt:
        return 130
    except OSError as exc:
        print(f"Error: failed to launch web server: {exc}", file=sys.stderr)
        return 1


def _current_workspace_has_active_web_manager() -> bool:
    from pbi_agent.session_store import SessionStore

    directory = current_workspace_context().directory_key
    with SessionStore() as store:
        return store.has_active_web_manager_lease(
            directory,
            stale_after_seconds=WEB_MANAGER_LEASE_STALE_SECONDS,
        )


def _resolve_web_command_port(args: argparse.Namespace) -> bool:
    if getattr(args, "_explicit_web_port", False):
        return True
    if args.port != DEFAULT_WEB_PORT:
        return True
    if _is_web_port_available(args.host, args.port):
        return True

    free_port = _find_free_web_port(args.host)
    if free_port is None:
        print("Error: unable to find a free port for the web server.", file=sys.stderr)
        return False

    print(
        f"Port {DEFAULT_WEB_PORT} is unavailable; using port {free_port}.",
        file=sys.stderr,
    )
    args.port = free_port
    return True


def _is_web_port_available(host: str, port: int) -> bool:
    try:
        with _bind_web_port_probe(host, port):
            return True
    except OSError:
        return False


def _find_free_web_port(host: str) -> int | None:
    try:
        with _bind_web_port_probe(host, 0) as probe:
            return int(probe.getsockname()[1])
    except OSError:
        return None


@contextlib.contextmanager
def _bind_web_port_probe(host: str, port: int):
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        yield sock
    finally:
        sock.close()


def _browser_target_url(args: argparse.Namespace) -> str:
    if args.url:
        parsed = urlparse(args.url)
        if parsed.scheme:
            return args.url
        return f"http://{args.url}"

    host = args.host
    if host == "0.0.0.0":
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"

    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{args.port}"


def _wait_for_web_server(
    host: str,
    port: int,
    timeout_seconds: float = WEB_SERVER_BROWSER_WAIT_TIMEOUT_SECONDS,
) -> WebServerWaitResult:
    connect_host = host
    if host == "0.0.0.0":
        connect_host = "127.0.0.1"
    elif host == "::":
        connect_host = "::1"

    start_time = time.monotonic()
    deadline = start_time + timeout_seconds
    attempts = 0
    last_error: str | None = None
    while time.monotonic() < deadline:
        attempts += 1
        try:
            with socket.create_connection(
                (connect_host, port),
                timeout=WEB_SERVER_BROWSER_CONNECT_TIMEOUT_SECONDS,
            ):
                return WebServerWaitResult(
                    ready=True,
                    connect_host=connect_host,
                    port=port,
                    timeout_seconds=timeout_seconds,
                    elapsed_seconds=time.monotonic() - start_time,
                    attempts=attempts,
                    last_error=last_error,
                )
        except OSError as exc:
            last_error = str(exc)
            time.sleep(WEB_SERVER_BROWSER_POLL_INTERVAL_SECONDS)
    return WebServerWaitResult(
        ready=False,
        connect_host=connect_host,
        port=port,
        timeout_seconds=timeout_seconds,
        elapsed_seconds=time.monotonic() - start_time,
        attempts=attempts,
        last_error=last_error,
    )


def _start_browser_open_thread(
    host: str,
    port: int,
    browser_url: str,
    *,
    ready_grace_seconds: float = 0.0,
    status_message: str | None = None,
) -> None:
    threading.Thread(
        target=_open_browser_when_ready,
        args=(host, port, browser_url),
        kwargs={
            "ready_grace_seconds": ready_grace_seconds,
            "status_message": status_message,
        },
        name="pbi-agent-web-browser",
        daemon=True,
    ).start()


def _open_browser_when_ready(
    host: str,
    port: int,
    browser_url: str,
    *,
    ready_grace_seconds: float = 0.0,
    status_message: str | None = None,
) -> None:
    result = _wait_for_web_server_with_optional_status(host, port, status_message)
    if result:
        _sleep_before_browser_open(ready_grace_seconds, status_message)
        if not _open_browser_url(browser_url):
            LOGGER.warning("Failed to open browser for %s", browser_url)
        return

    LOGGER.warning(
        (
            "Timed out waiting for the web server to start before opening %s "
            "(host=%s port=%s waited=%.1fs attempts=%s last_error=%s). "
            "Retrying browser launch for up to %.1fs."
        ),
        browser_url,
        result.connect_host,
        result.port,
        result.elapsed_seconds,
        result.attempts,
        result.last_error or "none",
        WEB_SERVER_BROWSER_WAIT_RETRY_SECONDS,
    )

    retry_result = _wait_for_web_server_with_optional_status(
        host,
        port,
        status_message,
        timeout_seconds=WEB_SERVER_BROWSER_WAIT_RETRY_SECONDS,
    )
    if retry_result:
        _sleep_before_browser_open(ready_grace_seconds, status_message)
        if not _open_browser_url(browser_url):
            LOGGER.warning("Failed to open browser for %s", browser_url)
        return

    LOGGER.warning(
        (
            "Web server still was not reachable for browser launch: %s "
            "(host=%s port=%s waited=%.1fs attempts=%s last_error=%s)."
        ),
        browser_url,
        retry_result.connect_host,
        retry_result.port,
        retry_result.elapsed_seconds,
        retry_result.attempts,
        retry_result.last_error or "none",
    )


def _wait_for_web_server_with_optional_status(
    host: str,
    port: int,
    status_message: str | None,
    *,
    timeout_seconds: float = WEB_SERVER_BROWSER_WAIT_TIMEOUT_SECONDS,
) -> WebServerWaitResult:
    if not status_message:
        return _wait_for_web_server(host, port, timeout_seconds=timeout_seconds)

    from rich.console import Console

    console = Console(file=sys.stderr)
    with console.status(status_message, spinner="dots"):
        return _wait_for_web_server(host, port, timeout_seconds=timeout_seconds)


def _sleep_before_browser_open(
    ready_grace_seconds: float,
    status_message: str | None,
) -> None:
    if ready_grace_seconds <= 0:
        return

    if not status_message:
        time.sleep(ready_grace_seconds)
        return

    from rich.console import Console

    console = Console(file=sys.stderr)
    with console.status(status_message, spinner="dots"):
        time.sleep(ready_grace_seconds)


def _open_browser_url(browser_url: str) -> bool:
    if os.environ.get("BROWSER"):
        return webbrowser.open(browser_url)

    if _is_wsl_environment() and _open_url_in_windows_browser(browser_url):
        return True

    return webbrowser.open(browser_url)


def _is_wsl_environment() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True

    try:
        return (
            "microsoft"
            in Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
        )
    except OSError:
        return False


def _open_url_in_windows_browser(browser_url: str) -> bool:
    commands = (
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"Start-Process -FilePath {_powershell_single_quote(browser_url)}",
        ],
        ["cmd.exe", "/c", f'start "" "{browser_url}"'],
    )

    for command in commands:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            continue

        time.sleep(0.1)
        return_code = process.poll()
        if return_code is None or return_code == 0:
            return True

    return False


def _powershell_single_quote(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _create_web_server(
    args: argparse.Namespace,
    settings: Settings | ResolvedRuntime,
) -> object:
    from pbi_agent.web.serve import PBIWebServer

    runtime = _coerce_runtime(settings)

    return PBIWebServer(
        settings=runtime,
        runtime_args=args,
        host=args.host,
        port=args.port,
        title=args.title,
        public_url=args.url,
    )


def _load_session_record(session_id: str):
    from pbi_agent.session_store import SessionStore

    try:
        store = SessionStore()
    except Exception as exc:
        print(f"Error: unable to open session store: {exc}", file=sys.stderr)
        return None

    with store:
        session = store.get_session(session_id)

    if session is None:
        print(f"Error: session '{session_id}' not found.", file=sys.stderr)
        return None
    return session
