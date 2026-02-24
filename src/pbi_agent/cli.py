from __future__ import annotations

import argparse
import json
import logging
import sys

from pbi_agent.agent.protocol import ProtocolError
from pbi_agent.agent.session import run_chat_loop, run_single_turn
from pbi_agent.agent.ws_client import WebSocketClientError
from pbi_agent.config import ConfigError, resolve_settings
from pbi_agent.log_config import configure_logging
from pbi_agent.tools.registry import get_tool_spec, get_tool_specs

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pbi-agent",
        description="Power BI editing coding agent (foundation v1).",
    )
    parser.add_argument("--model", help="Override model name.")
    parser.add_argument("--ws-url", help="Override Responses API websocket URL.")
    parser.add_argument("--api-key", help="Override OPENAI_API_KEY.")
    parser.add_argument(
        "--max-tool-workers",
        type=int,
        default=None,
        help="Maximum parallel workers for tool execution.",
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

    tools_parser = subparsers.add_parser("tools", help="Inspect tool registry.")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command", required=True)
    tools_subparsers.add_parser("list", help="List registered tools.")
    describe_parser = tools_subparsers.add_parser("describe", help="Describe one tool.")
    describe_parser.add_argument("--name", required=True, help="Tool name.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = resolve_settings(args)
        configure_logging(settings.verbose)

        if args.command == "tools":
            return _handle_tools_command(args)

        settings.validate()
        LOGGER.debug("Resolved settings: %s", settings.redacted())

        if args.command == "run":
            outcome = run_single_turn(args.prompt, settings)
            return 4 if outcome.tool_errors else 0
        if args.command == "chat":
            return run_chat_loop(settings)
        parser.error("Unknown command.")
        return 1
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except (WebSocketClientError, ProtocolError) as exc:
        print(f"WebSocket/protocol error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # pragma: no cover - defensive fallback
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


def _handle_tools_command(args: argparse.Namespace) -> int:
    if args.tools_command == "list":
        tools = get_tool_specs()
        if not tools:
            print("No tools registered.")
            return 0
        for tool in tools:
            print(f"{tool.name}: {tool.description}")
        return 0

    if args.tools_command == "describe":
        tool = get_tool_spec(args.name)
        if tool is None:
            print(f"Unknown tool: {args.name}", file=sys.stderr)
            return 1
        print(f"name: {tool.name}")
        print(f"description: {tool.description}")
        print(f"is_destructive: {tool.is_destructive}")
        print("parameters_schema:")
        print(json.dumps(tool.parameters_schema, indent=2))
        return 0

    return 1

