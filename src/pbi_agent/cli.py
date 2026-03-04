from __future__ import annotations

import argparse
import json
import logging
import sys

from pathlib import Path

from pbi_agent.config import ConfigError, Settings, resolve_settings
from pbi_agent.init_command import init_report
from pbi_agent.log_config import configure_logging
from pbi_agent.tools.registry import get_tool_spec, get_tool_specs

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pbi-agent",
        description="Power BI editing coding agent (foundation v1).",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic"],
        default=None,
        help="LLM provider backend (default: openai).",
    )
    parser.add_argument("--model", help="Override model name.")
    parser.add_argument("--ws-url", help="Override Responses API websocket URL.")
    parser.add_argument("--api-key", help="Override OPENAI_API_KEY.")
    parser.add_argument(
        "--anthropic-api-key",
        help="Override ANTHROPIC_API_KEY.",
    )
    parser.add_argument(
        "--anthropic-model",
        help="Override Anthropic model name (default: claude-opus-4-6).",
    )
    parser.add_argument(
        "--anthropic-max-tokens",
        type=int,
        default=None,
        help="Max output tokens for Anthropic (default: 16384).",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high", "xhigh"],
        default=None,
        help="Set model reasoning effort (default: medium).",
    )
    parser.add_argument(
        "--max-tool-workers",
        type=int,
        default=None,
        help="Maximum parallel workers for tool execution.",
    )
    parser.add_argument(
        "--ws-max-retries",
        type=int,
        default=None,
        help=(
            "Maximum retries for transient websocket failures and rate-limit responses."
        ),
    )
    parser.add_argument(
        "--compact-threshold",
        type=int,
        default=150000,
        help="Context compaction token threshold (default: 150000).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logs.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a single prompt turn.")
    run_parser.add_argument("--prompt", required=True, help="User prompt.")

    subparsers.add_parser("chat", help="Run an interactive chat loop.")
    audit_parser = subparsers.add_parser(
        "audit",
        help="Run report audit mode and write AUDIT-REPORT.md.",
    )
    audit_parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("."),
        help="Relative report directory to audit (default: current directory).",
    )

    tools_parser = subparsers.add_parser("tools", help="Inspect tool registry.")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command", required=True)
    tools_subparsers.add_parser("list", help="List registered tools.")
    describe_parser = tools_subparsers.add_parser("describe", help="Describe one tool.")
    describe_parser.add_argument("--name", required=True, help="Tool name.")

    init_parser = subparsers.add_parser(
        "init",
        help="Scaffold a new Power BI report project from the bundled template.",
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # ---- commands that don't need settings or the TUI ----

    if args.command == "tools":
        return _handle_tools_command(args)

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

    parser.error("Unknown command.")
    return 1


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _handle_chat_command(settings: Settings) -> int:
    from pbi_agent.display import ChatApp

    app = ChatApp(settings=settings, verbose=settings.verbose)
    app.run()
    return app.exit_code


def _handle_run_command(args: argparse.Namespace, settings: Settings) -> int:
    from pbi_agent.display import ChatApp

    app = ChatApp(
        settings=settings,
        verbose=settings.verbose,
        mode="run",
        prompt=args.prompt,
    )
    app.run()
    return app.exit_code


def _handle_audit_command(args: argparse.Namespace, settings: Settings) -> int:
    from pbi_agent.agent.audit_prompt import (
        AUDIT_REPORT_FILENAME,
        AUDIT_TODO_FILENAME,
        build_audit_prompt,
    )
    from pbi_agent.display import ChatApp

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
    app.run()

    report_path = report_dir / AUDIT_REPORT_FILENAME
    if not report_path.exists():
        print(
            f"Error: Audit mode completed but did not produce "
            f"{AUDIT_REPORT_FILENAME} in {report_dir}",
            file=sys.stderr,
        )
        return app.exit_code or 1

    print(f"Audit report written to {report_path}")
    return app.exit_code


# ---------------------------------------------------------------------------
# Non-TUI command handlers
# ---------------------------------------------------------------------------


_BUILTIN_TOOLS: dict[str, str] = {
    "apply_patch": "Create, update, or delete files using v4a diff patches.",
    "shell": "Execute shell commands in the workspace directory.",
}


def _brief(description: str) -> str:
    """Return the first sentence or line of a description."""
    first_line = description.split("\n", 1)[0].strip()
    dot = first_line.find(". ")
    if dot != -1:
        return first_line[: dot + 1]
    return first_line


def _handle_tools_command(args: argparse.Namespace) -> int:
    if args.tools_command == "list":
        # Built-in tools
        for name, desc in _BUILTIN_TOOLS.items():
            print(f"  {name} (built-in): {desc}")
        # Registered function tools
        for tool in get_tool_specs():
            print(f"  {tool.name}: {_brief(tool.description)}")
        return 0

    if args.tools_command == "describe":
        # Check built-in tools first
        if args.name in _BUILTIN_TOOLS:
            print(f"name: {args.name}")
            print("type: built-in")
            print(f"description: {_BUILTIN_TOOLS[args.name]}")
            return 0
        # Check registered function tools
        tool = get_tool_spec(args.name)
        if tool is None:
            all_names = list(_BUILTIN_TOOLS.keys()) + [t.name for t in get_tool_specs()]
            print(f"Unknown tool: {args.name}")
            print(f"Available: {', '.join(all_names)}")
            return 1
        print(f"name: {tool.name}")
        print("type: function")
        print(f"description: {tool.description}")
        print(f"is_destructive: {tool.is_destructive}")
        print("parameters_schema:")
        print(json.dumps(tool.parameters_schema, indent=2))
        return 0

    return 1


def _handle_init_command(args: argparse.Namespace) -> int:
    dest = args.dest or Path.cwd()
    try:
        init_report(dest, force=args.force)
        print(f"Report template created in {dest}")
        return 0
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
