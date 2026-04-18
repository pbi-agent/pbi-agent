from __future__ import annotations

import argparse
import contextlib
import dataclasses
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

from pbi_agent.auth.cli_flow import (
    run_provider_browser_auth_flow,
    run_provider_device_auth_flow,
)
from pbi_agent.auth.models import (
    AUTH_FLOW_METHOD_BROWSER,
    AUTH_FLOW_METHOD_DEVICE,
    AUTH_MODE_API_KEY,
    AUTH_MODE_CHATGPT_ACCOUNT,
)
from pbi_agent.auth.service import (
    delete_provider_auth_session,
    get_provider_auth_status,
    import_provider_auth_session,
    refresh_provider_auth_session,
)
from pbi_agent.config import (
    ConfigError,
    ModelProfileConfig,
    OPENAI_SERVICE_TIERS,
    PROVIDER_KINDS,
    ProviderConfig,
    ResolvedRuntime,
    Settings,
    create_model_profile_config,
    create_provider_config,
    delete_model_profile_config,
    delete_provider_config,
    list_model_profile_configs,
    list_provider_configs,
    resolve_runtime,
    resolve_web_runtime,
    select_active_model_profile,
    slugify,
    update_model_profile_config,
    update_provider_config,
)
from pbi_agent.init_command import init_report
from pbi_agent.log_config import configure_logging

LOGGER = logging.getLogger(__name__)
DEFAULT_COMMAND = "web"
WEB_SERVER_BROWSER_WAIT_TIMEOUT_SECONDS = 20.0
WEB_SERVER_BROWSER_WAIT_RETRY_SECONDS = 10.0
WEB_SERVER_BROWSER_POLL_INTERVAL_SECONDS = 0.1
WEB_SERVER_BROWSER_CONNECT_TIMEOUT_SECONDS = 0.2


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
        "--profile-id",
        dest="profile_id",
        default=None,
        help="Select a saved profile ID before applying explicit overrides.",
    )
    model_group.add_argument(
        "--model",
        help="Override the provider model; omit this for generic default routing.",
    )
    model_group.add_argument(
        "--sub-agent-model",
        dest="sub_agent_model",
        help="Override the sub_agent model; defaults to the provider-specific sub-agent model.",
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
    model_group.add_argument(
        "--no-web-search",
        dest="no_web_search",
        action="store_true",
        default=False,
        help="Disable the provider's native web search tool.",
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
    diagnostics_group.add_argument(
        "--skills",
        action="store_true",
        help="List discovered project skills from .agents/skills and exit.",
    )
    diagnostics_group.add_argument(
        "--mcp",
        action="store_true",
        help="List discovered project MCP servers from .agents and exit.",
    )
    diagnostics_group.add_argument(
        "--agents",
        action="store_true",
        help="List discovered project sub-agents from .agents/*.md and exit.",
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
        "--image",
        dest="images",
        action="append",
        default=[],
        help="Attach a local workspace image to the prompt. Repeatable.",
    )
    run_parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("."),
        help="Relative project directory to scope tool execution to (default: current directory).",
    )
    run_parser.add_argument(
        "--session-id",
        help="Resume a previous session by ID to continue the conversation.",
    )

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
        help="Enable web development mode.",
    )
    web_parser.add_argument(
        "--title",
        default=None,
        help="Optional browser title override.",
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

    config_parser = add_command_parser(
        "config", "Manage saved providers and model profiles."
    )
    config_subparsers = config_parser.add_subparsers(
        dest="config_scope",
        required=True,
        metavar="<scope>",
    )

    providers_parser = config_subparsers.add_parser(
        "providers",
        prog="pbi-agent config providers",
        description="Manage saved provider connection settings.",
        help="Manage saved providers.",
        formatter_class=CleanHelpFormatter,
    )
    providers_actions = providers_parser.add_subparsers(
        dest="config_action",
        required=True,
        metavar="<action>",
    )
    providers_actions.add_parser(
        "list",
        prog="pbi-agent config providers list",
        description="List saved providers.",
        help="List saved providers.",
        formatter_class=CleanHelpFormatter,
    )
    providers_create = providers_actions.add_parser(
        "create",
        prog="pbi-agent config providers create",
        description="Create a saved provider.",
        help="Create a saved provider.",
        formatter_class=CleanHelpFormatter,
    )
    providers_create.add_argument("--name", required=True, help="Display name.")
    providers_create.add_argument(
        "--id",
        default=None,
        help="Stable provider ID slug. Defaults to a slug derived from --name.",
    )
    providers_create.add_argument(
        "--kind",
        choices=list(PROVIDER_KINDS),
        required=True,
        help="Provider backend kind.",
    )
    providers_create.add_argument(
        "--auth-mode",
        choices=[AUTH_MODE_API_KEY, AUTH_MODE_CHATGPT_ACCOUNT],
        default=AUTH_MODE_API_KEY,
        help="Provider authentication mode.",
    )
    providers_create.add_argument("--api-key", dest="provider_api_key")
    providers_create.add_argument("--api-key-env", default=None)
    providers_create.add_argument("--responses-url")
    providers_create.add_argument("--generic-api-url")

    providers_update = providers_actions.add_parser(
        "update",
        prog="pbi-agent config providers update",
        description="Update a saved provider.",
        help="Update a saved provider.",
        formatter_class=CleanHelpFormatter,
    )
    providers_update.add_argument("provider_id", help="Provider ID.")
    providers_update.add_argument("--name", default=None, help="Display name.")
    providers_update.add_argument(
        "--kind",
        choices=list(PROVIDER_KINDS),
        default=None,
        help="Provider backend kind.",
    )
    providers_update.add_argument(
        "--auth-mode",
        choices=[AUTH_MODE_API_KEY, AUTH_MODE_CHATGPT_ACCOUNT],
        default=None,
        help="Provider authentication mode.",
    )
    providers_update.add_argument("--api-key", dest="provider_api_key", default=None)
    providers_update.add_argument("--api-key-env", default=None)
    providers_update.add_argument("--responses-url", default=None)
    providers_update.add_argument("--generic-api-url", default=None)

    providers_delete = providers_actions.add_parser(
        "delete",
        prog="pbi-agent config providers delete",
        description="Delete a saved provider.",
        help="Delete a saved provider.",
        formatter_class=CleanHelpFormatter,
    )
    providers_delete.add_argument("provider_id", help="Provider ID.")

    providers_auth_status = providers_actions.add_parser(
        "auth-status",
        prog="pbi-agent config providers auth-status",
        description="Show stored auth session status for a provider.",
        help="Show provider auth status.",
        formatter_class=CleanHelpFormatter,
    )
    providers_auth_status.add_argument("provider_id", help="Provider ID.")

    providers_auth_login = providers_actions.add_parser(
        "auth-login",
        prog="pbi-agent config providers auth-login",
        description="Run a built-in browser or device login flow for a provider.",
        help="Run provider auth login flow.",
        formatter_class=CleanHelpFormatter,
    )
    providers_auth_login.add_argument("provider_id", help="Provider ID.")
    providers_auth_login.add_argument(
        "--method",
        choices=[AUTH_FLOW_METHOD_BROWSER, AUTH_FLOW_METHOD_DEVICE],
        default=AUTH_FLOW_METHOD_BROWSER,
        help="Built-in auth flow method to run.",
    )

    providers_auth_import = providers_actions.add_parser(
        "auth-import",
        prog="pbi-agent config providers auth-import",
        description="Import an account session for a provider.",
        help="Import provider auth session.",
        formatter_class=CleanHelpFormatter,
    )
    providers_auth_import.add_argument("provider_id", help="Provider ID.")
    providers_auth_import.add_argument("--access-token", required=True)
    providers_auth_import.add_argument("--refresh-token", default=None)
    providers_auth_import.add_argument("--account-id", default=None)
    providers_auth_import.add_argument("--email", default=None)
    providers_auth_import.add_argument("--plan-type", default=None)
    providers_auth_import.add_argument("--expires-at", type=int, default=None)
    providers_auth_import.add_argument("--id-token", default=None)

    providers_auth_refresh = providers_actions.add_parser(
        "auth-refresh",
        prog="pbi-agent config providers auth-refresh",
        description="Refresh a stored account session for a provider.",
        help="Refresh provider auth session.",
        formatter_class=CleanHelpFormatter,
    )
    providers_auth_refresh.add_argument("provider_id", help="Provider ID.")

    providers_auth_logout = providers_actions.add_parser(
        "auth-logout",
        prog="pbi-agent config providers auth-logout",
        description="Delete a stored account session for a provider.",
        help="Delete provider auth session.",
        formatter_class=CleanHelpFormatter,
    )
    providers_auth_logout.add_argument("provider_id", help="Provider ID.")

    profiles_parser = config_subparsers.add_parser(
        "profiles",
        prog="pbi-agent config profiles",
        description="Manage saved model profiles.",
        help="Manage saved model profiles.",
        formatter_class=CleanHelpFormatter,
    )
    profiles_actions = profiles_parser.add_subparsers(
        dest="config_action",
        required=True,
        metavar="<action>",
    )
    profiles_actions.add_parser(
        "list",
        prog="pbi-agent config profiles list",
        description="List saved model profiles.",
        help="List saved model profiles.",
        formatter_class=CleanHelpFormatter,
    )

    def add_profile_options(
        target: argparse.ArgumentParser, *, require_provider_id: bool
    ) -> None:
        target.add_argument(
            "--provider-id",
            required=require_provider_id,
            default=None,
            help="Saved provider ID backing this profile.",
        )
        target.add_argument("--model", default=None, help="Main model.")
        target.add_argument(
            "--sub-agent-model",
            dest="sub_agent_model",
            default=None,
            help="Sub-agent model override.",
        )
        target.add_argument(
            "--reasoning-effort",
            choices=["low", "medium", "high", "xhigh"],
            default=None,
            help="Requested reasoning effort.",
        )
        target.add_argument("--max-tokens", type=int, default=None)
        target.add_argument(
            "--service-tier",
            choices=list(OPENAI_SERVICE_TIERS),
            default=None,
            help="OpenAI service tier.",
        )
        web_search_group = target.add_mutually_exclusive_group()
        web_search_group.add_argument(
            "--web-search",
            dest="web_search",
            action="store_true",
            default=None,
            help="Enable native web search for this profile.",
        )
        web_search_group.add_argument(
            "--no-web-search",
            dest="web_search",
            action="store_false",
            help="Disable native web search for this profile.",
        )
        target.add_argument("--max-tool-workers", type=int, default=None)
        target.add_argument("--max-retries", type=int, default=None)
        target.add_argument("--compact-threshold", type=int, default=None)

    profiles_create = profiles_actions.add_parser(
        "create",
        prog="pbi-agent config profiles create",
        description="Create a saved model profile.",
        help="Create a saved model profile.",
        formatter_class=CleanHelpFormatter,
    )
    profiles_create.add_argument("--name", required=True, help="Display name.")
    profiles_create.add_argument(
        "--id",
        default=None,
        help="Stable model profile ID slug. Defaults to a slug derived from --name.",
    )
    add_profile_options(profiles_create, require_provider_id=True)

    profiles_update = profiles_actions.add_parser(
        "update",
        prog="pbi-agent config profiles update",
        description="Update a saved model profile.",
        help="Update a saved model profile.",
        formatter_class=CleanHelpFormatter,
    )
    profiles_update.add_argument("profile_id", help="Model profile ID.")
    profiles_update.add_argument("--name", default=None, help="Display name.")
    add_profile_options(profiles_update, require_provider_id=False)

    profiles_delete = profiles_actions.add_parser(
        "delete",
        prog="pbi-agent config profiles delete",
        description="Delete a saved model profile.",
        help="Delete a saved model profile.",
        formatter_class=CleanHelpFormatter,
    )
    profiles_delete.add_argument("profile_id", help="Model profile ID.")

    profiles_select = profiles_actions.add_parser(
        "select",
        prog="pbi-agent config profiles select",
        description="Set the default saved model profile for the web UI.",
        help="Select the default web model profile.",
        formatter_class=CleanHelpFormatter,
    )
    profiles_select.add_argument("profile_id", help="Model profile ID.")

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


def _web_runtime_flags_in_args(raw_argv: list[str]) -> list[str]:
    runtime_flags = {
        "--provider",
        "--responses-url",
        "--api-key",
        "--openai-api-key",
        "--xai-api-key",
        "--google-api-key",
        "--anthropic-api-key",
        "--generic-api-key",
        "--generic-api-url",
        "--profile-id",
        "--model",
        "--sub-agent-model",
        "--max-tokens",
        "--reasoning-effort",
        "--service-tier",
        "--no-web-search",
        "--max-tool-workers",
        "--max-retries",
        "--compact-threshold",
    }
    seen: list[str] = []
    for token in raw_argv:
        flag = token.split("=", 1)[0]
        if flag in runtime_flags:
            seen.append(flag)
    return seen


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(_argv_with_default_command(parser, raw_argv))

    # ---- commands that don't need settings ----

    if args.skills:
        return _handle_skills_flag(args)
    if args.mcp:
        return _handle_mcp_flag(args)
    if args.agents:
        return _handle_agents_flag(args)

    if args.command == "init":
        return _handle_init_command(args)

    if args.command == "sessions":
        return _handle_sessions_command(args)

    if args.command == "config":
        try:
            return _handle_config_command(args)
        except ConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

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
                "`--profile-id` or explicit runtime flags only with `run` or `audit`.",
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
        return _handle_web_command(args, runtime)

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

    if args.command == "audit":
        return _handle_audit_command(args, runtime)

    parser.error("Unknown command.")
    return 1


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _handle_config_command(args: argparse.Namespace) -> int:
    if args.config_scope == "providers":
        return _handle_config_providers_command(args)
    if args.config_scope == "profiles":
        return _handle_config_profiles_command(args)
    raise ConfigError(f"Unknown config scope '{args.config_scope}'.")


def _handle_config_providers_command(args: argparse.Namespace) -> int:
    from rich.console import Console
    from rich.table import Table

    console = Console(width=160)

    if args.config_action == "list":
        providers = list_provider_configs()
        if not providers:
            console.print("[dim]No saved providers.[/dim]")
            return 0
        table = Table(title="Saved Providers", title_style="bold cyan")
        table.add_column("ID", style="green")
        table.add_column("Name")
        table.add_column("Kind", style="yellow")
        table.add_column("Auth Mode", style="yellow")
        table.add_column("Auth Status")
        table.add_column("API Key")
        table.add_column("Responses URL")
        table.add_column("Generic API URL")
        for provider in providers:
            table.add_row(
                provider.id,
                provider.name,
                provider.kind,
                provider.auth_mode,
                _format_provider_auth_status(provider),
                _display_secret(provider.api_key),
                provider.responses_url or "",
                provider.generic_api_url or "",
            )
        console.print(table)
        return 0

    if args.config_action == "create":
        provider, _ = create_provider_config(
            ProviderConfig(
                id=slugify(args.id or args.name),
                name=args.name,
                kind=args.kind,
                auth_mode=args.auth_mode,
                api_key=args.provider_api_key or "",
                api_key_env=args.api_key_env,
                responses_url=args.responses_url,
                generic_api_url=args.generic_api_url,
            )
        )
        print(f"Created provider '{provider.id}'.")
        return 0

    if args.config_action == "update":
        provider, _ = update_provider_config(
            args.provider_id,
            name=args.name,
            kind=args.kind,
            auth_mode=args.auth_mode,
            api_key=args.provider_api_key,
            api_key_env=args.api_key_env,
            responses_url=args.responses_url,
            generic_api_url=args.generic_api_url,
        )
        print(f"Updated provider '{provider.id}'.")
        return 0

    if args.config_action == "delete":
        delete_provider_config(args.provider_id)
        print(f"Deleted provider '{slugify(args.provider_id)}'.")
        return 0

    if args.config_action == "auth-status":
        provider = _require_provider_config(args.provider_id)
        _print_provider_auth_status(provider)
        return 0

    if args.config_action == "auth-login":
        provider = _require_provider_config(args.provider_id)
        if args.method == AUTH_FLOW_METHOD_BROWSER:
            result = run_provider_browser_auth_flow(
                provider_kind=provider.kind,
                provider_id=provider.id,
                auth_mode=provider.auth_mode,
                open_browser=_open_browser_url,
                on_ready=_print_browser_auth_instructions,
            )
            print(
                f"Connected auth session for '{provider.id}'"
                + (f" ({result.session.email})" if result.session.email else "")
                + "."
            )
            _print_provider_auth_status(provider)
            return 0

        result = run_provider_device_auth_flow(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
            on_start=_print_device_auth_instructions,
        )
        print(
            f"Connected auth session for '{provider.id}'"
            + (f" ({result.session.email})" if result.session.email else "")
            + "."
        )
        _print_provider_auth_status(provider)
        return 0

    if args.config_action == "auth-import":
        provider = _require_provider_config(args.provider_id)
        session = import_provider_auth_session(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
            payload={
                "access_token": args.access_token,
                "refresh_token": args.refresh_token,
                "account_id": args.account_id,
                "email": args.email,
                "plan_type": args.plan_type,
                "expires_at": args.expires_at,
                "id_token": args.id_token,
            },
        )
        print(
            f"Imported auth session for '{provider.id}'"
            + (f" ({session.email})" if session.email else "")
            + "."
        )
        _print_provider_auth_status(provider)
        return 0

    if args.config_action == "auth-refresh":
        provider = _require_provider_config(args.provider_id)
        session = refresh_provider_auth_session(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        print(
            f"Refreshed auth session for '{provider.id}'"
            + (f" ({session.email})" if session.email else "")
            + "."
        )
        _print_provider_auth_status(provider)
        return 0

    if args.config_action == "auth-logout":
        provider = _require_provider_config(args.provider_id)
        removed = delete_provider_auth_session(provider.id)
        if removed:
            print(f"Deleted auth session for '{provider.id}'.")
        else:
            print(f"No stored auth session for '{provider.id}'.")
        _print_provider_auth_status(provider)
        return 0

    raise ConfigError(f"Unknown providers action '{args.config_action}'.")


def _handle_config_profiles_command(args: argparse.Namespace) -> int:
    from rich.console import Console
    from rich.table import Table

    console = Console()

    if args.config_action == "list":
        profiles, active_profile_id = list_model_profile_configs()
        if not profiles:
            console.print("[dim]No saved model profiles.[/dim]")
            return 0
        table = Table(title="Saved Model Profiles", title_style="bold cyan")
        table.add_column("ID", style="green")
        table.add_column("Active", style="yellow")
        table.add_column("Name")
        table.add_column("Provider", style="yellow")
        table.add_column("Model")
        table.add_column("Sub-Agent")
        table.add_column("Reasoning")
        for profile in profiles:
            table.add_row(
                profile.id,
                "yes" if profile.id == active_profile_id else "",
                profile.name,
                profile.provider_id,
                profile.model or "",
                profile.sub_agent_model or "",
                profile.reasoning_effort or "",
            )
        console.print(table)
        return 0

    if args.config_action == "create":
        profile, _ = create_model_profile_config(
            ModelProfileConfig(
                id=slugify(args.id or args.name),
                name=args.name,
                provider_id=args.provider_id,
                model=args.model,
                sub_agent_model=args.sub_agent_model,
                reasoning_effort=args.reasoning_effort,
                max_tokens=args.max_tokens,
                service_tier=args.service_tier,
                web_search=args.web_search,
                max_tool_workers=args.max_tool_workers,
                max_retries=args.max_retries,
                compact_threshold=args.compact_threshold,
            )
        )
        print(f"Created model profile '{profile.id}'.")
        return 0

    if args.config_action == "update":
        profile, _ = update_model_profile_config(
            args.profile_id,
            name=args.name,
            provider_id=args.provider_id,
            model=args.model,
            sub_agent_model=args.sub_agent_model,
            reasoning_effort=args.reasoning_effort,
            max_tokens=args.max_tokens,
            service_tier=args.service_tier,
            web_search=args.web_search,
            max_tool_workers=args.max_tool_workers,
            max_retries=args.max_retries,
            compact_threshold=args.compact_threshold,
        )
        print(f"Updated model profile '{profile.id}'.")
        return 0

    if args.config_action == "delete":
        delete_model_profile_config(args.profile_id)
        print(f"Deleted model profile '{slugify(args.profile_id)}'.")
        return 0

    if args.config_action == "select":
        active_id, _ = select_active_model_profile(args.profile_id)
        print(f"Selected web model profile '{active_id}'.")
        return 0

    raise ConfigError(f"Unknown profiles action '{args.config_action}'.")


def _display_secret(value: str) -> str:
    return value and f"{value[:4]}...{value[-4:]}" if value else ""


def _require_provider_config(provider_id: str) -> ProviderConfig:
    normalized_id = slugify(provider_id)
    for provider in list_provider_configs():
        if provider.id == normalized_id:
            return provider
    raise ConfigError(f"Unknown provider ID '{provider_id}'.")


def _provider_auth_status(provider: ProviderConfig):
    return get_provider_auth_status(
        provider_kind=provider.kind,
        provider_id=provider.id,
        auth_mode=provider.auth_mode,
    )


def _format_provider_auth_status(provider: ProviderConfig) -> str:
    if provider.auth_mode == AUTH_MODE_API_KEY:
        if provider.api_key_env:
            return f"env:{provider.api_key_env}"
        if provider.api_key:
            return "configured"
        return "missing"
    status = _provider_auth_status(provider)
    if status.email:
        return f"{status.session_status}:{status.email}"
    if status.plan_type:
        return f"{status.session_status}:{status.plan_type}"
    return status.session_status


def _print_provider_auth_status(provider: ProviderConfig) -> None:
    status = _provider_auth_status(provider)
    print(f"Provider: {provider.id}")
    print(f"Kind: {provider.kind}")
    print(f"Auth mode: {status.auth_mode}")
    print(f"Session status: {status.session_status}")
    print(f"Backend: {status.backend or 'n/a'}")
    print(f"Can refresh: {'yes' if status.can_refresh else 'no'}")
    if status.email:
        print(f"Email: {status.email}")
    if status.account_id:
        print(f"Account ID: {status.account_id}")
    if status.plan_type:
        print(f"Plan: {status.plan_type}")
    if status.expires_at is not None:
        print(f"Expires at: {status.expires_at}")


def _print_browser_auth_instructions(browser_auth) -> None:
    print("Open this URL to complete provider authorization:")
    print(browser_auth.authorization_url)
    print(f"Waiting for callback on {browser_auth.redirect_uri} ...")


def _print_device_auth_instructions(device_auth) -> None:
    print("Open this URL and enter the one-time code to authorize the provider:")
    print(device_auth.verification_url)
    print(f"Code: {device_auth.user_code}")
    print("Waiting for device authorization ...")


def _handle_skills_flag(args: argparse.Namespace) -> int:
    from pbi_agent.agent.skill_discovery import discover_project_skills
    from rich.console import Console
    from rich.table import Table

    target_dir = _workspace_directory_for_args(args)
    skills = discover_project_skills(workspace=target_dir)
    console = Console()

    if not skills:
        console.print("[dim]No project skills discovered under[/dim] .agents/skills/")
        return 0

    table = Table(title="Project Skills", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Location", style="dim")
    for skill in skills:
        table.add_row(skill.name, skill.description, str(skill.location))
    console.print(table)
    return 0


def _handle_mcp_flag(args: argparse.Namespace) -> int:
    from pbi_agent.mcp import discover_mcp_server_configs
    from rich.console import Console
    from rich.table import Table

    target_dir = _workspace_directory_for_args(args)
    servers = discover_mcp_server_configs(workspace=target_dir)
    console = Console()

    if not servers:
        console.print("[dim]No project MCP servers discovered under[/dim] .agents/")
        return 0

    table = Table(title="MCP Servers", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Transport", style="yellow")
    table.add_column("Command / URL")
    table.add_column("Config", style="dim")
    for server in servers:
        if server.transport == "http":
            detail = server.url or ""
        else:
            detail = " ".join([server.command or "", *server.args]).strip()
        table.add_row(server.name, server.transport, detail, str(server.location))
    console.print(table)
    return 0


def _handle_agents_flag(args: argparse.Namespace) -> int:
    from pbi_agent.agent.sub_agent_discovery import discover_project_sub_agents
    from rich.console import Console
    from rich.table import Table

    target_dir = _workspace_directory_for_args(args)
    agents = discover_project_sub_agents(workspace=target_dir)
    console = Console()

    if not agents:
        console.print("[dim]No project sub-agents discovered under[/dim] .agents/*.md")
        return 0

    table = Table(title="Sub-Agents", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Model", style="yellow")
    table.add_column("Reasoning", style="yellow")
    for agent in agents:
        table.add_row(
            agent.name,
            agent.description,
            agent.model or "default",
            agent.reasoning_effort or "default",
        )
    console.print(table)
    return 0


def _workspace_directory_for_args(args: argparse.Namespace) -> Path:
    if getattr(args, "command", None) == "run" and getattr(args, "project_dir", None):
        return (Path.cwd() / args.project_dir).resolve()
    if getattr(args, "command", None) == "audit" and getattr(args, "report_dir", None):
        return (Path.cwd() / args.report_dir).resolve()
    return Path.cwd().resolve()


def _coerce_runtime(settings: Settings | ResolvedRuntime) -> ResolvedRuntime:
    if isinstance(settings, ResolvedRuntime):
        return settings
    return ResolvedRuntime(settings=settings, provider_id="", profile_id="")


def _handle_run_command(
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


def _handle_audit_command(
    args: argparse.Namespace,
    settings: Settings | ResolvedRuntime,
) -> int:
    runtime = _coerce_runtime(settings)
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
            settings=runtime,
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
    settings: Settings | ResolvedRuntime,
    single_turn_hint: str | None = None,
    image_paths: list[str] | None = None,
    resume_session_id: str | None = None,
) -> int:
    from pbi_agent.agent.error_formatting import format_user_facing_error
    from pbi_agent.agent.session import run_single_turn
    from pbi_agent.display.console_display import ConsoleDisplay

    runtime = _coerce_runtime(settings)
    display = ConsoleDisplay(verbose=runtime.settings.verbose)

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


def _handle_web_command(
    args: argparse.Namespace,
    settings: Settings | ResolvedRuntime,
) -> int:
    runtime = _coerce_runtime(settings)
    if args.port < 1 or args.port > 65535:
        print("Error: --port must be between 1 and 65535.", file=sys.stderr)
        return 2

    browser_url = _browser_target_url(args)
    print(f"Serving web UI on {browser_url}")
    _start_browser_open_thread(args.host, args.port, browser_url)

    server = _create_web_server(
        args,
        runtime,
    )
    try:
        with _temporary_env_overrides(_settings_env(runtime.settings)):
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


def _start_browser_open_thread(host: str, port: int, browser_url: str) -> None:
    threading.Thread(
        target=_open_browser_when_ready,
        args=(host, port, browser_url),
        name="pbi-agent-web-browser",
        daemon=True,
    ).start()


def _open_browser_when_ready(host: str, port: int, browser_url: str) -> None:
    result = _wait_for_web_server(host, port)
    if result:
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

    retry_result = _wait_for_web_server(
        host,
        port,
        timeout_seconds=WEB_SERVER_BROWSER_WAIT_RETRY_SECONDS,
    )
    if retry_result:
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


def _handle_init_command(args: argparse.Namespace) -> int:
    dest = args.dest or Path.cwd()
    try:
        init_report(dest, force=args.force)
        print(f"Report template created in {dest}")
        return 0
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
