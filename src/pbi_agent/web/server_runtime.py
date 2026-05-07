from __future__ import annotations

import argparse
import contextlib
import logging
import signal
import threading
from collections.abc import Callable

from fastapi import FastAPI
from rich.console import Console
import uvicorn
import uvicorn.server

from pbi_agent.branding import startup_panel
from pbi_agent.config import ConfigError, ResolvedRuntime, Settings, resolve_web_runtime
from pbi_agent.web.app_factory import create_app
from pbi_agent.web.defaults import DEFAULT_WEB_PORT
from pbi_agent.web.session_manager import WebManagerStartupError


class PBIWebServer:
    def __init__(
        self,
        *,
        settings: Settings,
        runtime_args: argparse.Namespace | None = None,
        host: str = "127.0.0.1",
        port: int = DEFAULT_WEB_PORT,
        title: str | None = None,
        public_url: str | None = None,
    ) -> None:
        self._settings = settings
        self._runtime_args = runtime_args
        self.host = host
        self.port = port
        self.title = title
        self.public_url = public_url
        self.console = Console(highlight=False)
        self._startup_warning: str | None = None

    def serve(self, debug: bool = False) -> None:
        app = create_app(
            self._settings,
            runtime_args=self._runtime_args,
            debug=debug,
            title=self.title,
            public_url=self.public_url,
        )
        target = self.public_url or f"http://{self.host}:{self.port}"
        self.console.print(startup_panel(), highlight=False)
        self.console.print(f"  Serving on [bold]{target}[/bold]")
        self.console.print("[cyan]  Press Ctrl+C to quit[/cyan]")
        server = _GracefulUvicornServer(
            uvicorn.Config(
                app=app,
                host=self.host,
                port=self.port,
                log_level="info" if debug else "warning",
                lifespan="on",
            )
        )
        server.startup_failure_callback = self._set_startup_warning
        try:
            server.run()
        except KeyboardInterrupt:
            return
        if self._startup_warning is not None:
            self.console.print(f"[yellow]Warning:[/yellow] {self._startup_warning}")

    def _set_startup_warning(self, message: str) -> None:
        self._startup_warning = message


class _GracefulUvicornServer(uvicorn.Server):
    startup_failure_callback: Callable[[str], None] | None = None

    def run(self, sockets=None) -> None:  # type: ignore[no-untyped-def]
        with _suppress_expected_startup_tracebacks(self._record_startup_failure):
            super().run(sockets=sockets)

    def _record_startup_failure(self, message: str) -> None:
        if self.startup_failure_callback is not None:
            self.startup_failure_callback(message)

    @contextlib.contextmanager
    def capture_signals(self):
        if threading.current_thread() is not threading.main_thread():
            yield
            return

        handled_signals = getattr(
            uvicorn.server,
            "HANDLED_SIGNALS",
            (signal.SIGINT, signal.SIGTERM),
        )
        original_handlers = {
            sig: signal.signal(sig, self.handle_exit) for sig in handled_signals
        }
        try:
            yield
        finally:
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)


@contextlib.contextmanager
def _suppress_expected_startup_tracebacks(
    record_startup_failure: Callable[[str], None],
):
    logger = logging.getLogger("uvicorn.error")
    log_filter = _ExpectedStartupFailureFilter(record_startup_failure)
    logger.addFilter(log_filter)
    try:
        yield
    finally:
        logger.removeFilter(log_filter)


class _ExpectedStartupFailureFilter(logging.Filter):
    def __init__(self, record_startup_failure: Callable[[str], None] | None = None):
        super().__init__()
        self._record_startup_failure = record_startup_failure

    def filter(self, record: logging.LogRecord) -> bool:
        exc_info = record.exc_info
        if exc_info is not None and isinstance(exc_info[1], WebManagerStartupError):
            self._record(str(exc_info[1]))
            return False
        message = record.getMessage()
        startup_error_message = _startup_error_message_from_traceback(message)
        if startup_error_message is not None:
            self._record(startup_error_message)
            return False
        if (
            message == "Application startup failed. Exiting."
            and record.exc_info is None
        ):
            return False
        return True

    def _record(self, message: str) -> None:
        if self._record_startup_failure is not None:
            self._record_startup_failure(message)


def _startup_error_message_from_traceback(message: str) -> str | None:
    marker = "pbi_agent.web.session_manager.WebManagerStartupError: "
    for line in reversed(message.splitlines()):
        if marker in line:
            return line.split(marker, 1)[1].strip()
    subclass_marker = "pbi_agent.web.session_manager.WebManager"
    suffix = "Error: "
    for line in reversed(message.splitlines()):
        if subclass_marker in line and suffix in line:
            return line.split(suffix, 1)[1].strip()
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="pbi-agent web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_WEB_PORT)
    parser.add_argument("--title", default=None)
    parser.add_argument("--url", default=None, dest="public_url")
    parser.add_argument("--dev", action="store_true", default=False)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--sub-agent-model", default="gpt-5.4-mini")
    parser.add_argument(
        "--responses-url", default="https://api.openai.com/v1/responses"
    )
    parser.add_argument(
        "--generic-api-url", default="https://openrouter.ai/api/v1/chat/completions"
    )
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--max-tool-workers", type=int, default=4)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--compact-threshold", type=int, default=200000)
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--service-tier", default=None)
    parser.add_argument("--no-web-search", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        runtime: Settings | ResolvedRuntime = resolve_web_runtime(verbose=args.verbose)
    except ConfigError:
        runtime = Settings(api_key="", provider="openai", model="gpt-5.4")
    PBIWebServer(
        settings=runtime,
        runtime_args=args,
        host=args.host,
        port=args.port,
        title=args.title,
        public_url=args.public_url,
    ).serve(debug=args.dev)


def default_settings_namespace() -> argparse.Namespace:
    return argparse.Namespace(
        api_key=None,
        provider=None,
        responses_url=None,
        generic_api_url=None,
        profile_id=None,
        model=None,
        sub_agent_model=None,
        max_tokens=None,
        verbose=False,
        max_tool_workers=None,
        max_retries=None,
        reasoning_effort=None,
        compact_threshold=None,
        service_tier=None,
        no_web_search=False,
    )


def create_default_fastapi_app() -> FastAPI:
    args = default_settings_namespace()
    try:
        runtime: Settings | ResolvedRuntime = resolve_web_runtime(verbose=args.verbose)
    except ConfigError:
        runtime = Settings(api_key="", provider="openai", model="gpt-5.4")
    return create_app(runtime, runtime_args=args)
