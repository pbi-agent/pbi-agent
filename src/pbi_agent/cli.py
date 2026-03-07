from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys

from pathlib import Path

from pbi_agent.config import ConfigError, Settings, resolve_settings
from pbi_agent.init_command import init_report
from pbi_agent.log_config import configure_logging

LOGGER = logging.getLogger(__name__)
DEFAULT_COMMAND = "web"


class CleanHelpFormatter(argparse.HelpFormatter):
    """Tune help layout for clearer row-based CLI output."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=36, width=100)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pbi-agent",
        description="Power BI editing coding agent (foundation v1).",
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
        choices=["openai", "anthropic", "generic"],
        default=None,
        help="LLM provider backend (default: openai).",
    )
    provider_group.add_argument(
        "--ws-url", help="Override Responses API websocket URL."
    )
    provider_group.add_argument(
        "--responses-url",
        help="Override OpenAI Responses HTTP API URL.",
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
        help="Override generic OpenAI-compatible Chat Completions URL.",
    )

    model_group = parser.add_argument_group("Model behavior")
    model_group.add_argument(
        "--model",
        help="Override model name for the selected provider; omit for generic provider default routing.",
    )
    model_group.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Max output tokens for providers that support token limits (default: 16384).",
    )
    model_group.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high", "xhigh"],
        default=None,
        help="Set model reasoning effort (default: medium).",
    )

    runtime_group = parser.add_argument_group("Runtime and resilience")
    runtime_group.add_argument(
        "--max-tool-workers",
        type=int,
        default=None,
        help="Maximum parallel workers for tool execution.",
    )
    runtime_group.add_argument(
        "--ws-max-retries",
        type=int,
        default=None,
        help=(
            "Maximum retries for transient websocket failures and rate-limit responses."
        ),
    )
    runtime_group.add_argument(
        "--compact-threshold",
        type=int,
        default=150000,
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

    run_parser = subparsers.add_parser(
        "run",
        help="Run a single prompt turn.",
        formatter_class=CleanHelpFormatter,
    )
    run_parser.add_argument("--prompt", required=True, help="User prompt.")

    subparsers.add_parser(
        "chat",
        help="Run an interactive chat loop.",
        formatter_class=CleanHelpFormatter,
    )
    web_parser = subparsers.add_parser(
        "web",
        help="Serve the chat UI in a browser via textual serve.",
        formatter_class=CleanHelpFormatter,
    )
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

    audit_parser = subparsers.add_parser(
        "audit",
        help="Run report audit mode and write AUDIT-REPORT.md.",
        formatter_class=CleanHelpFormatter,
    )
    audit_parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("."),
        help="Relative report directory to audit (default: current directory).",
    )

    init_parser = subparsers.add_parser(
        "init",
        help="Scaffold a new Power BI report project from the bundled template.",
        formatter_class=CleanHelpFormatter,
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

    # ---- resolve settings for interactive/session commands ----

    try:
        settings = resolve_settings(args)
        configure_logging(settings.verbose)
        settings.validate()
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    LOGGER.debug("Resolved settings: %s", settings.redacted())

    if args.command == "run":
        return _handle_run_command(args, settings)

    if args.command == "chat":
        return _handle_chat_command(settings)

    if args.command == "audit":
        return _handle_audit_command(args, settings)

    if args.command == "web":
        return _handle_web_command(args, settings)

    parser.error("Unknown command.")
    return 1


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _handle_chat_command(settings: Settings) -> int:
    from pbi_agent.ui import ChatApp

    app = ChatApp(settings=settings, verbose=settings.verbose)
    return _run_app(app)


def _handle_run_command(args: argparse.Namespace, settings: Settings) -> int:
    from pbi_agent.ui import ChatApp

    app = ChatApp(
        settings=settings,
        verbose=settings.verbose,
        mode="run",
        prompt=args.prompt,
    )
    return _run_app(app)


def _handle_audit_command(args: argparse.Namespace, settings: Settings) -> int:
    from pbi_agent.agent.audit_prompt import (
        AUDIT_REPORT_FILENAME,
        AUDIT_TODO_FILENAME,
        build_audit_prompt,
    )
    from pbi_agent.ui import ChatApp

    report_dir_input = args.report_dir or Path(".")
    report_dir = (Path.cwd() / report_dir_input).resolve()

    if not report_dir.exists():
        print(f"Error: Report directory does not exist: {report_dir}", file=sys.stderr)
        return 1
    if not report_dir.is_dir():
        print(f"Error: Report path is not a directory: {report_dir}", file=sys.stderr)
        return 1

    app = ChatApp(
        settings=settings,
        verbose=settings.verbose,
        mode="audit",
        prompt=build_audit_prompt(),
        audit_report_dir=report_dir,
        single_turn_hint=(
            f"Audit mode: Evaluating report and writing "
            f"{AUDIT_TODO_FILENAME} progress tracker and "
            f"AUDIT-REPORT.md."
        ),
    )
    exit_code = _run_app(app)
    if app.fatal_error_message:
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
    selected_model = settings.model
    if settings.provider == "anthropic":
        selected_model = settings.anthropic_model
    env: dict[str, str] = {
        "PBI_AGENT_PROVIDER": settings.provider,
        "PBI_AGENT_API_KEY": settings.api_key,
        "PBI_AGENT_WS_URL": settings.ws_url,
        "PBI_AGENT_RESPONSES_URL": settings.responses_url,
        "PBI_AGENT_GENERIC_API_URL": settings.generic_api_url,
        "PBI_AGENT_MODEL": selected_model,
        "PBI_AGENT_REASONING_EFFORT": settings.reasoning_effort,
        "PBI_AGENT_MAX_TOOL_WORKERS": str(settings.max_tool_workers),
        "PBI_AGENT_WS_MAX_RETRIES": str(settings.ws_max_retries),
        "PBI_AGENT_COMPACT_THRESHOLD": str(settings.compact_threshold),
        "PBI_AGENT_MAX_TOKENS": str(settings.anthropic_max_tokens),
    }
    return env


def _handle_web_command(args: argparse.Namespace, settings: Settings) -> int:
    if args.port < 1 or args.port > 65535:
        print("Error: --port must be between 1 and 65535.", file=sys.stderr)
        return 2

    python_dir = Path(sys.executable).parent
    textual_candidates = [
        python_dir / "textual.exe",
        python_dir / "textual.cmd",
        python_dir / "textual",
    ]
    textual_cli = next(
        (str(path) for path in textual_candidates if path.exists()), None
    )
    if textual_cli is None:
        textual_cli = shutil.which("textual")
    if textual_cli is None:
        print(
            "Error: `textual` command not found in the current runtime. Install "
            "textual-dev in this environment to use `pbi-agent web`.",
            file=sys.stderr,
        )
        return 2

    chat_command: list[str] = [sys.executable, "-m", "pbi_agent"]
    if settings.verbose:
        chat_command.append("--verbose")
    chat_command.append("chat")

    serve_cmd: list[str] = [
        textual_cli,
        "serve",
        "--command",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.dev:
        serve_cmd.append("--dev")
    if args.title:
        serve_cmd.extend(["--title", args.title])
    if args.url:
        serve_cmd.extend(["--url", args.url])
    serve_cmd.append(subprocess.list2cmdline(chat_command))

    env = os.environ.copy()
    env.update(_settings_env(settings))

    print(f"Serving web UI on http://{args.host}:{args.port}")
    try:
        completed = subprocess.run(serve_cmd, env=env, check=False)
    except OSError as exc:
        print(f"Error: failed to launch textual serve: {exc}", file=sys.stderr)
        return 1
    return completed.returncode


def _handle_init_command(args: argparse.Namespace) -> int:
    dest = args.dest or Path.cwd()
    try:
        init_report(dest, force=args.force)
        print(f"Report template created in {dest}")
        return 0
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
