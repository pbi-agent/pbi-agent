from __future__ import annotations

import argparse
import contextlib
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

from pathlib import Path
from urllib.parse import urlparse

from pbi_agent.config import (
    ConfigError,
    OPENAI_SERVICE_TIERS,
    Settings,
    resolve_settings,
    save_internal_config,
)
from pbi_agent.init_command import init_report
from pbi_agent.log_config import configure_logging
from pbi_agent.session_store import SessionRecord

LOGGER = logging.getLogger(__name__)
DEFAULT_COMMAND = "web"


class CleanHelpFormatter(argparse.HelpFormatter):
    """Tune help layout for clearer row-based CLI output."""

    MIN_WIDTH = 100
    MAX_WIDTH = 120
    MAX_HELP_POSITION = 42

    def __init__(self, prog: str) -> None:
        terminal_width = shutil.get_terminal_size(fallback=(self.MAX_WIDTH, 24)).columns
        help_width = min(max(terminal_width, self.MIN_WIDTH), self.MAX_WIDTH)
        help_position = min(self.MAX_HELP_POSITION, max(30, (help_width // 3) + 2))
        super().__init__(prog, max_help_position=help_position, width=help_width)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pbi-agent",
        description="Local CLI agent for creating, auditing, and editing Power BI PBIP reports.",
        usage="%(prog)s [GLOBAL OPTIONS] [<command>] [COMMAND OPTIONS]",
        epilog=(
            "Run `pbi-agent <command> --help` for command-specific options. "
            "Defaults to `web` when no command is provided."
        ),
        formatter_class=CleanHelpFormatter,
        allow_abbrev=False,
    )
    provider_group = parser.add_argument_group("Provider and API")
    provider_group.add_argument(
        "--provider",
        choices=["openai", "xai", "google", "anthropic", "generic"],
        metavar="PROVIDER",
        default=None,
        help=(
            "Provider backend: openai, xai, google, anthropic, or generic "
            "(default: openai)."
        ),
    )
    provider_group.add_argument(
        "--responses-url",
        help="Override the provider API URL (Responses or Interactions).",
    )
    provider_group.add_argument(
        "--api-key",
        dest="api_key",
        help="Override PBI_AGENT_API_KEY.",
    )
    provider_group.add_argument(
        "--openai-api-key",
        dest="api_key",
        help=argparse.SUPPRESS,
    )
    provider_group.add_argument(
        "--xai-api-key",
        dest="api_key",
        help=argparse.SUPPRESS,
    )
    provider_group.add_argument(
        "--google-api-key",
        dest="api_key",
        help=argparse.SUPPRESS,
    )
    provider_group.add_argument(
        "--anthropic-api-key",
        dest="api_key",
        help=argparse.SUPPRESS,
    )
    provider_group.add_argument(
        "--generic-api-key",
        dest="api_key",
        help=argparse.SUPPRESS,
    )
    provider_group.add_argument(
        "--generic-api-url",
        help="Override the generic OpenAI-compatible Chat Completions URL.",
    )

    model_group = parser.add_argument_group("Model behavior")
    model_group.add_argument(
        "--model",
        help="Override the provider model; omit this for generic default routing.",
    )
    model_group.add_argument(
        "--sub-agent-model",
        dest="sub_agent_model",
        help="Override the sub_agent model; defaults to --model.",
    )
    model_group.add_argument(
        "--max-tokens",
        dest="max_tokens",
        type=int,
        default=None,
        help="Max output tokens for the selected provider (default: 16384).",
    )
    model_group.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high", "xhigh"],
        metavar="LEVEL",
        default=None,
        help="Reasoning effort: low, medium, high, or xhigh.",
    )
    model_group.add_argument(
        "--service-tier",
        choices=list(OPENAI_SERVICE_TIERS),
        metavar="TIER",
        default=None,
        help="OpenAI service tier: auto, default, flex, or priority.",
    )

    runtime_group = parser.add_argument_group("Runtime and resilience")
    runtime_group.add_argument(
        "--max-tool-workers",
        type=int,
        default=None,
        help="Maximum parallel workers for tool execution.",
    )
    runtime_group.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Maximum retries for transient failures and rate-limit responses.",
    )
    runtime_group.add_argument(
        "--compact-threshold",
        type=int,
        default=None,
        help="Context compaction token threshold (default: 150000).",
    )

    diagnostics_group = parser.add_argument_group("Diagnostics")
    diagnostics_group.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logs.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=False,
        title="Commands",
        metavar="<command>",
    )

    def add_command_parser(name: str, help_text: str) -> argparse.ArgumentParser:
        return subparsers.add_parser(
            name,
            prog=f"pbi-agent {name}",
            description=help_text,
            help=help_text,
            formatter_class=CleanHelpFormatter,
        )

    run_parser = add_command_parser("run", "Run a single prompt turn.")
    run_parser.add_argument("--prompt", required=True, help="User prompt.")
    run_parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("."),
        help="Relative project directory to scope tool execution to (default: current directory).",
    )

    add_command_parser("console", "Run an interactive terminal session.")
    web_parser = add_command_parser("web", "Serve the browser interface.")
    web_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the web server (default: 127.0.0.1).",
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the web server (default: 8000).",
    )
    web_parser.add_argument(
        "--dev",
        action="store_true",
        help="Enable textual web dev mode.",
    )
    web_parser.add_argument(
        "--title",
        default=None,
        help="Optional browser title shown by textual serve.",
    )
    web_parser.add_argument(
        "--url",
        default=None,
        help="Optional public URL for reverse-proxy setups.",
    )

    audit_parser = add_command_parser(
        "audit", "Audit a report and write AUDIT-REPORT.md."
    )
    audit_parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("."),
        help="Relative report directory to audit (default: current directory).",
    )

    sessions_parser = add_command_parser(
        "sessions", "List past sessions for the current directory."
    )
    sessions_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of sessions to show (default: 20).",
    )
    sessions_parser.add_argument(
        "--all-dirs",
        action="store_true",
        help="Show sessions from all directories, not just the current one.",
    )

    open_parser = add_command_parser("open", "Resume a previous session by ID.")
    open_parser.add_argument(
        "--session-id",
        required=True,
        help="Session ID to resume.",
    )

    init_parser = add_command_parser(
        "init", "Create a report project from the bundled template."
    )
    init_parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Target directory (defaults to current directory).",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files if they already exist.",
    )

    return parser


def _argv_with_default_command(
    parser: argparse.ArgumentParser, raw_argv: list[str]
) -> list[str]:
    argv = list(raw_argv)
    if not argv:
        return [DEFAULT_COMMAND]

    insert_at = _default_command_insertion_index(parser, argv)
    if insert_at is None:
        return argv
    return [*argv[:insert_at], DEFAULT_COMMAND, *argv[insert_at:]]


def _default_command_insertion_index(
    parser: argparse.ArgumentParser, argv: list[str]
) -> int | None:
    command_names = _subcommand_names(parser)
    option_actions = parser._option_string_actions
    index = 0

    while index < len(argv):
        token = argv[index]

        if token in command_names or token in {"-h", "--help"}:
            return None
        if token == "--":
            return index
        if not token.startswith("-"):
            return index

        option_token = token
        if token.startswith("--") and "=" in token:
            option_token = token.split("=", 1)[0]
            action = option_actions.get(option_token)
            if action is None:
                return index
            index += 1
            continue

        action = option_actions.get(option_token)
        if action is None:
            return index
        if action.nargs == 0:
            index += 1
            continue
        if index + 1 >= len(argv):
            return None
        index += 2

    return len(argv)


def _subcommand_names(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(_argv_with_default_command(parser, raw_argv))

    # ---- commands that don't need settings or the TUI ----

    if args.command == "init":
        return _handle_init_command(args)

    if args.command == "sessions":
        return _handle_sessions_command(args)

    if args.command == "open":
        _open_session = _load_session_record(args.session_id)
        if _open_session is None:
            return 1
        args.provider = _open_session.provider
        if not args.model:
            args.model = _open_session.model

    # ---- resolve settings for interactive/session commands ----

    try:
        settings = resolve_settings(args)
        configure_logging(settings.verbose)
        settings.validate()
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    LOGGER.debug("Resolved settings: %s", settings.redacted())
    try:
        save_internal_config(settings)
    except OSError as exc:
        LOGGER.warning("Unable to persist internal config: %s", exc)

    if args.command == "run":
        return _handle_run_command(args, settings)

    if args.command == "console":
        return _handle_console_command(settings)

    if args.command == "open":
        return _handle_open_command(args, settings, _open_session)

    if args.command == "audit":
        return _handle_audit_command(args, settings)

    if args.command == "web":
        return _handle_web_command(args, settings)

    parser.error("Unknown command.")
    return 1


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _handle_console_command(settings: Settings) -> int:
    from pbi_agent.ui import ChatApp

    app = ChatApp(settings=settings, verbose=settings.verbose)
    return _run_app(app)


def _handle_run_command(args: argparse.Namespace, settings: Settings) -> int:
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
            settings=settings,
        )
    finally:
        os.chdir(original_cwd)


def _handle_audit_command(args: argparse.Namespace, settings: Settings) -> int:
    from pbi_agent.agent.error_formatting import format_user_facing_error
    from pbi_agent.agent.audit_prompt import (
        AUDIT_REPORT_FILENAME,
        AUDIT_TODO_FILENAME,
        build_audit_prompt,
        copy_audit_todo,
    )

    report_dir_input = args.report_dir or Path(".")
    report_dir = (Path.cwd() / report_dir_input).resolve()

    if not report_dir.exists():
        print(f"Error: Report directory does not exist: {report_dir}", file=sys.stderr)
        return 1
    if not report_dir.is_dir():
        print(f"Error: Report path is not a directory: {report_dir}", file=sys.stderr)
        return 1

    original_cwd = Path.cwd()
    try:
        os.chdir(report_dir)
        copy_audit_todo(report_dir)
        exit_code = _run_single_turn_command(
            prompt=build_audit_prompt(),
            settings=settings,
            single_turn_hint=(
                f"Audit mode: Evaluating report and writing "
                f"{AUDIT_TODO_FILENAME} progress tracker and "
                f"{AUDIT_REPORT_FILENAME}."
            ),
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        _print_error(format_user_facing_error(exc))
        return 1
    finally:
        os.chdir(original_cwd)

    if exit_code in {1, 130}:
        return exit_code

    report_path = report_dir / AUDIT_REPORT_FILENAME
    if not report_path.exists():
        print(
            f"Error: Audit mode completed but did not produce "
            f"{AUDIT_REPORT_FILENAME} in {report_dir}",
            file=sys.stderr,
        )
        return exit_code or 1

    print(f"Audit report written to {report_path}")
    return exit_code


def _run_single_turn_command(
    *,
    prompt: str,
    settings: Settings,
    single_turn_hint: str | None = None,
) -> int:
    from pbi_agent.agent.error_formatting import format_user_facing_error
    from pbi_agent.agent.session import run_single_turn
    from pbi_agent.ui.console_display import ConsoleDisplay

    display = ConsoleDisplay(verbose=settings.verbose)

    try:
        outcome = run_single_turn(
            prompt,
            settings,
            display,
            single_turn_hint=single_turn_hint,
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        _print_error(format_user_facing_error(exc))
        return 1

    return 4 if outcome.tool_errors else 0


def _run_app(app: object) -> int:
    app.run()
    fatal_error_message = getattr(app, "fatal_error_message", None)
    if isinstance(fatal_error_message, str) and fatal_error_message.strip():
        _print_error(fatal_error_message)
    exit_code = getattr(app, "exit_code", 0)
    return exit_code if isinstance(exit_code, int) else 0


def _print_error(message: str) -> None:
    lines = [line for line in message.splitlines() if line.strip()]
    if not lines:
        print("Error.", file=sys.stderr)
        return
    print(f"Error: {lines[0]}", file=sys.stderr)
    for line in lines[1:]:
        print(line, file=sys.stderr)


def _settings_env(settings: Settings) -> dict[str, str]:
    env: dict[str, str] = {
        "PBI_AGENT_PROVIDER": settings.provider,
        "PBI_AGENT_API_KEY": settings.api_key,
        "PBI_AGENT_RESPONSES_URL": settings.responses_url,
        "PBI_AGENT_GENERIC_API_URL": settings.generic_api_url,
        "PBI_AGENT_MODEL": settings.model,
        "PBI_AGENT_SUB_AGENT_MODEL": settings.sub_agent_model or "",
        "PBI_AGENT_REASONING_EFFORT": settings.reasoning_effort,
        "PBI_AGENT_MAX_TOOL_WORKERS": str(settings.max_tool_workers),
        "PBI_AGENT_MAX_RETRIES": str(settings.max_retries),
        "PBI_AGENT_COMPACT_THRESHOLD": str(settings.compact_threshold),
        "PBI_AGENT_MAX_TOKENS": str(settings.max_tokens),
    }
    if settings.service_tier:
        env["PBI_AGENT_SERVICE_TIER"] = settings.service_tier
    return env


@contextlib.contextmanager
def _temporary_env_overrides(env_updates: dict[str, str]):
    previous = {key: os.environ.get(key) for key in env_updates}
    os.environ.update(env_updates)
    try:
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _handle_web_command(args: argparse.Namespace, settings: Settings) -> int:
    if args.port < 1 or args.port > 65535:
        print("Error: --port must be between 1 and 65535.", file=sys.stderr)
        return 2

    browser_url = _browser_target_url(args)
    print(f"Serving web UI on {browser_url}")
    _start_browser_open_thread(args.host, args.port, browser_url)

    server = _create_web_server(
        args,
        _web_chat_command(settings, parent_pid=os.getpid()),
    )
    try:
        with _temporary_env_overrides(_settings_env(settings)):
            server.serve(debug=args.dev)
            return 0
    except KeyboardInterrupt:
        return 130
    except OSError as exc:
        print(f"Error: failed to launch web server: {exc}", file=sys.stderr)
        return 1


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


def _wait_for_web_server(host: str, port: int, timeout_seconds: float = 10.0) -> bool:
    connect_host = host
    if host == "0.0.0.0":
        connect_host = "127.0.0.1"
    elif host == "::":
        connect_host = "::1"

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((connect_host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _start_browser_open_thread(host: str, port: int, browser_url: str) -> None:
    threading.Thread(
        target=_open_browser_when_ready,
        args=(host, port, browser_url),
        name="pbi-agent-web-browser",
        daemon=True,
    ).start()


def _open_browser_when_ready(host: str, port: int, browser_url: str) -> None:
    if _wait_for_web_server(host, port):
        if not _open_browser_url(browser_url):
            LOGGER.warning("Failed to open browser for %s", browser_url)
        return

    LOGGER.warning(
        "Timed out waiting for the web server to start before opening %s",
        browser_url,
    )


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
        ["explorer.exe", browser_url],
        ["cmd.exe", "/c", "start", "", browser_url],
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


def _web_chat_command(settings: Settings, *, parent_pid: int) -> str:
    chat_command: list[str] = [
        sys.executable,
        "-m",
        "pbi_agent.web.chat_entry",
        "--parent-pid",
        str(parent_pid),
    ]
    if settings.verbose:
        chat_command.append("--verbose")
    return subprocess.list2cmdline(chat_command)


def _create_web_server(args: argparse.Namespace, command: str) -> object:
    from pbi_agent.web.serve import _FaviconServer

    return _FaviconServer(
        command=command,
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


def _handle_sessions_command(args: argparse.Namespace) -> int:
    from pbi_agent.session_store import SessionStore

    try:
        store = SessionStore()
    except Exception as exc:
        print(f"Error: unable to open session store: {exc}", file=sys.stderr)
        return 1

    with store:
        if args.all_dirs:
            sessions = store.list_all_sessions(limit=args.limit)
        else:
            sessions = store.list_sessions(os.getcwd(), limit=args.limit)

    if not sessions:
        print("No sessions found.")
        return 0

    header = (
        f"{'ID':<34} {'Provider':<12} {'Model':<24} "
        f"{'Title':<24} {'Tokens':>10} {'Cost':>8} {'Updated'}"
    )
    print(header)
    print("-" * len(header))
    for s in sessions:
        title = (s.title[:21] + "...") if len(s.title) > 24 else s.title
        updated = s.updated_at[:19].replace("T", " ")
        tokens = f"{s.total_tokens:,}" if s.total_tokens else "-"
        cost = f"${s.cost_usd:.4f}" if s.cost_usd else "-"
        print(
            f"{s.session_id:<34} {s.provider:<12} {s.model:<24} "
            f"{title:<24} {tokens:>10} {cost:>8} {updated}"
        )
    return 0


def _handle_open_command(
    args: argparse.Namespace,
    settings: Settings,
    session: SessionRecord,
) -> int:
    from pbi_agent.ui import ChatApp

    session_dir = Path(session.directory).expanduser()
    if not session_dir.exists():
        print(
            f"Error: saved session directory does not exist: {session_dir}",
            file=sys.stderr,
        )
        return 1
    if not session_dir.is_dir():
        print(
            f"Error: saved session directory is not a directory: {session_dir}",
            file=sys.stderr,
        )
        return 1

    original_cwd = Path.cwd()
    try:
        os.chdir(session_dir)
        app = ChatApp(
            settings=settings,
            verbose=settings.verbose,
            resume_session_id=args.session_id,
        )
        return _run_app(app)
    finally:
        os.chdir(original_cwd)


def _handle_init_command(args: argparse.Namespace) -> int:
    dest = args.dest or Path.cwd()
    try:
        init_report(dest, force=args.force)
        print(f"Report template created in {dest}")
        return 0
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
