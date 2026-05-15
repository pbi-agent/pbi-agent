from __future__ import annotations

import logging
import sys

from pbi_agent.config import (
    ConfigError,
    ResolvedRuntime,
    Settings,
    resolve_runtime,
    resolve_web_runtime,
)
from pbi_agent.log_config import configure_logging
from pbi_agent.maintenance import run_startup_maintenance

from .catalogs import (
    _handle_agents_command,
    _handle_agents_flag,
    _handle_commands_command,
    _handle_mcp_flag,
    _handle_skills_command,
)
from .config import _handle_config_command
from .kanban import _handle_kanban_command
from .parser import _argv_with_default_command, _web_runtime_flags_in_args, build_parser
from .run import _handle_run_command
from .sandbox import _handle_sandbox_command
from .sessions import _handle_sessions_command, _load_session_record
from .web import _handle_web_command

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(_argv_with_default_command(parser, raw_argv))
    maintenance_result = run_startup_maintenance(render_notice=args.command != "web")

    # ---- commands that don't need settings ----

    if args.mcp:
        return _handle_mcp_flag(args)
    if args.agents:
        return _handle_agents_flag(args)

    if args.command == "skills":
        return _handle_skills_command(args)

    if args.command == "commands":
        return _handle_commands_command(args)

    if args.command == "agents":
        return _handle_agents_command(args)

    if args.command == "sessions":
        return _handle_sessions_command(args)

    if args.command == "kanban":
        return _handle_kanban_command(args)

    if args.command == "config":
        try:
            return _handle_config_command(args)
        except ConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    if args.command == "sandbox":
        configure_logging(args.verbose)
        return _handle_sandbox_command(args)

    if args.command == "run" and args.session_id:
        _run_session = _load_session_record(args.session_id)
        if _run_session is None:
            return 1
        args.project_dir = _run_session.directory

    if args.command == "web":
        if _web_runtime_flags_in_args(raw_argv):
            print(
                "Error: runtime provider/model flags are no longer supported with "
                "`pbi-agent web`. Configure the web UI in Settings and use "
                "`--profile-id` or explicit runtime flags only with `run`.",
                file=sys.stderr,
            )
            return 2
        configure_logging(args.verbose)
        try:
            runtime: Settings | ResolvedRuntime = resolve_web_runtime(
                verbose=args.verbose
            )
            runtime.settings.validate()
        except ConfigError as exc:
            LOGGER.debug("Starting web UI without an active web profile: %s", exc)
            runtime = Settings(
                api_key="",
                provider="openai",
                model="gpt-5.4",
                verbose=args.verbose,
            )
        return _handle_web_command(
            args, runtime, update_notice=maintenance_result.update_notice
        )

    # ---- resolve settings for commands that need a provider ----

    try:
        runtime = resolve_runtime(args)
        settings = runtime.settings
        configure_logging(settings.verbose)
        settings.validate()
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    LOGGER.debug("Resolved settings: %s", settings.redacted())

    if args.command == "run":
        return _handle_run_command(args, runtime)

    parser.error("Unknown command.")
    return 1
