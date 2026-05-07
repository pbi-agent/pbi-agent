from __future__ import annotations

import argparse
import shutil

from pathlib import Path

from pbi_agent import __version__
from pbi_agent.auth.models import (
    AUTH_FLOW_METHOD_BROWSER,
    AUTH_FLOW_METHOD_DEVICE,
    AUTH_MODE_API_KEY,
    AUTH_MODE_CHATGPT_ACCOUNT,
    AUTH_MODE_COPILOT_ACCOUNT,
)
from pbi_agent.config import OPENAI_SERVICE_TIERS, PROVIDER_KINDS
from pbi_agent.web.defaults import DEFAULT_WEB_PORT

from .shared import DEFAULT_COMMAND, DEFAULT_SANDBOX_IMAGE


class ExplicitPortAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | int | None,
        option_string: str | None = None,
    ) -> None:
        del parser, option_string
        setattr(namespace, self.dest, values)
        setattr(namespace, "_explicit_web_port", True)


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
        description="Lightweight local coding agent.",
        usage="%(prog)s [GLOBAL OPTIONS] [<command>] [COMMAND OPTIONS]",
        epilog=(
            "Run `pbi-agent <command> --help` for command-specific options. "
            "Defaults to `web` when no command is provided."
        ),
        formatter_class=CleanHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=__version__,
        help="Show the current version and exit.",
    )
    provider_group = parser.add_argument_group("Provider and API")
    provider_group.add_argument(
        "--provider",
        choices=["openai", "azure", "xai", "google", "anthropic", "generic"],
        metavar="PROVIDER",
        default=None,
        help=(
            "Provider backend: openai, azure, xai, google, anthropic, or generic "
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
        "--azure-api-key",
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
        help=(
            "Override the sub_agent model; saved profiles without one use "
            "the profile main model."
        ),
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
        help="Context compaction token threshold (default: 200000).",
    )
    runtime_group.add_argument(
        "--compact-tail-turns",
        type=int,
        default=None,
        help="Recent user turns to preserve verbatim after compaction (default: 2).",
    )
    runtime_group.add_argument(
        "--compact-preserve-recent-tokens",
        type=int,
        default=None,
        help="Approximate token budget for preserved recent compaction tail (default: 8000).",
    )
    runtime_group.add_argument(
        "--compact-tool-output-max-chars",
        type=int,
        default=None,
        help="Maximum characters per tool-result string in compaction prompts (default: 2000).",
    )

    diagnostics_group = parser.add_argument_group("Diagnostics")
    diagnostics_group.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logs.",
    )
    diagnostics_group.add_argument(
        "--mcp",
        action="store_true",
        help="List discovered project MCP servers from .agents and exit.",
    )
    diagnostics_group.add_argument(
        "--agents",
        action="store_true",
        help="List discovered project sub-agents from .agents/agents/*.md and exit.",
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
        default=DEFAULT_WEB_PORT,
        action=ExplicitPortAction,
        help=f"Port to bind the web server (default: {DEFAULT_WEB_PORT}).",
    )
    web_parser.set_defaults(_explicit_web_port=False)
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
    web_parser.add_argument(
        "--no-open",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    sandbox_parser = add_command_parser(
        "sandbox",
        "Run pbi-agent inside a Docker Desktop sandbox.",
    )
    sandbox_parser.add_argument(
        "--image",
        default=DEFAULT_SANDBOX_IMAGE,
        help=f"Sandbox image name (default: {DEFAULT_SANDBOX_IMAGE}).",
    )
    sandbox_parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional env file to pass to the sandbox container.",
    )
    sandbox_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild the local sandbox image before running.",
    )
    sandbox_parser.add_argument(
        "--local-source",
        action="store_true",
        help="Install the mounted checkout in editable mode before running.",
    )
    sandbox_parser.add_argument(
        "--read-only-repo",
        action="store_true",
        help="Mount the current repository read-only inside the sandbox.",
    )
    sandbox_parser.add_argument(
        "-d",
        "--detach",
        action="store_true",
        help="Run the sandbox container in the background.",
    )
    sandbox_parser.set_defaults(
        sandbox_command="web",
        host="127.0.0.1",
        port=DEFAULT_WEB_PORT,
        _explicit_web_port=False,
        dev=False,
        title=None,
        url=None,
        no_open=False,
    )
    sandbox_subparsers = sandbox_parser.add_subparsers(
        dest="sandbox_command",
        metavar="<command>",
    )
    sandbox_web_parser = sandbox_subparsers.add_parser(
        "web",
        prog="pbi-agent sandbox web",
        description="Serve the browser interface inside the Docker sandbox.",
        help="Serve the browser interface inside the Docker sandbox.",
        formatter_class=CleanHelpFormatter,
    )
    sandbox_web_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to publish on the host (default: 127.0.0.1).",
    )
    sandbox_web_parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_WEB_PORT,
        action=ExplicitPortAction,
        help=f"Host and container web port (default: {DEFAULT_WEB_PORT}).",
    )
    sandbox_web_parser.set_defaults(_explicit_web_port=False)
    sandbox_web_parser.add_argument(
        "--dev",
        action="store_true",
        help="Enable web development mode inside the sandbox.",
    )
    sandbox_web_parser.add_argument(
        "--title",
        default=None,
        help="Optional browser title override.",
    )
    sandbox_web_parser.add_argument(
        "--url",
        default=None,
        help="Optional public URL for reverse-proxy setups.",
    )
    sandbox_run_parser = sandbox_subparsers.add_parser(
        "run",
        prog="pbi-agent sandbox run",
        description="Run a single prompt turn inside the Docker sandbox.",
        help="Run a single prompt turn inside the Docker sandbox.",
        formatter_class=CleanHelpFormatter,
    )
    sandbox_run_parser.add_argument("--prompt", required=True, help="User prompt.")
    sandbox_run_parser.add_argument(
        "--image",
        dest="images",
        action="append",
        default=[],
        help="Attach a local workspace image to the prompt. Repeatable.",
    )
    sandbox_run_parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("."),
        help="Relative project directory to scope tool execution to (default: current directory).",
    )
    sandbox_run_parser.add_argument(
        "--session-id",
        help="Resume a previous session by ID to continue the conversation.",
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

    kanban_parser = add_command_parser(
        "kanban", "Manage Kanban board tasks for the current workspace."
    )
    kanban_subparsers = kanban_parser.add_subparsers(
        dest="kanban_action",
        required=True,
        metavar="<action>",
    )
    kanban_create_parser = kanban_subparsers.add_parser(
        "create",
        prog="pbi-agent kanban create",
        description="Create a Kanban task in the current workspace board.",
        help="Create a Kanban task.",
        formatter_class=CleanHelpFormatter,
    )
    kanban_create_parser.add_argument(
        "--title",
        required=True,
        help="Task title shown on the Kanban card.",
    )
    kanban_create_parser.add_argument(
        "--desc",
        "--description",
        "--prompt",
        dest="desc",
        required=True,
        help="Task description/prompt to store on the card.",
    )
    kanban_create_parser.add_argument(
        "--lane",
        "--stage",
        "--state",
        dest="lane",
        default=None,
        help="Existing board stage by ID, name, or slugified name (default: first stage).",
    )
    kanban_create_parser.add_argument(
        "--project-dir",
        default=".",
        help="Workspace-relative project directory for future task runs (default: current directory).",
    )
    kanban_create_parser.add_argument(
        "--session-id",
        default=None,
        help="Optional existing session ID to associate with the task.",
    )
    kanban_create_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable JSON instead of a summary line.",
    )

    kanban_list_parser = kanban_subparsers.add_parser(
        "list",
        prog="pbi-agent kanban list",
        description="List Kanban tasks in the current workspace board.",
        help="List Kanban tasks.",
        formatter_class=CleanHelpFormatter,
    )
    kanban_list_parser.add_argument(
        "--stage",
        "--lane",
        "--state",
        dest="stage",
        default=None,
        help="Only show tasks in an existing board stage by ID, name, or slugified name (default: all stages).",
    )
    kanban_list_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable JSON instead of task detail blocks.",
    )

    skills_parser = add_command_parser(
        "skills", "List or install project-scoped skills."
    )
    skills_subparsers = skills_parser.add_subparsers(
        dest="skills_action",
        required=True,
        metavar="<action>",
    )
    skills_subparsers.add_parser(
        "list",
        prog="pbi-agent skills list",
        description="List installed project skills from .agents/skills.",
        help="List installed project skills.",
        formatter_class=CleanHelpFormatter,
    )
    skills_add_parser = skills_subparsers.add_parser(
        "add",
        prog="pbi-agent skills add",
        description=(
            "Install a project skill bundle from the official catalog, a local "
            "directory, or a GitHub repository."
        ),
        help="Install a project skill bundle.",
        formatter_class=CleanHelpFormatter,
    )
    skills_add_parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help=(
            "Optional source. Omit to use the official pbi-agent/skills catalog. "
            "Supports local paths, owner/repo, repository URLs, and tree URLs."
        ),
    )
    skills_add_parser.add_argument(
        "--skill",
        default=None,
        help="Select one skill from a multi-skill repository.",
    )
    skills_add_parser.add_argument(
        "--list",
        action="store_true",
        help="List remote candidate skills without installing anything.",
    )
    skills_add_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing local project skill install.",
    )

    commands_parser = add_command_parser(
        "commands", "List or install project-scoped commands."
    )
    commands_subparsers = commands_parser.add_subparsers(
        dest="commands_action",
        required=True,
        metavar="<action>",
    )
    commands_subparsers.add_parser(
        "list",
        prog="pbi-agent commands list",
        description="List installed project commands from .agents/commands.",
        help="List installed project commands.",
        formatter_class=CleanHelpFormatter,
    )
    commands_add_parser = commands_subparsers.add_parser(
        "add",
        prog="pbi-agent commands add",
        description=(
            "Install a project command from the official catalog, a local path, "
            "or a GitHub repository."
        ),
        help="Install a project command.",
        formatter_class=CleanHelpFormatter,
    )
    commands_add_parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help=(
            "Optional source. Omit to use the official pbi-agent/commands "
            "catalog. Supports local paths, owner/repo, repository URLs, and "
            "tree URLs."
        ),
    )
    commands_add_parser.add_argument(
        "--command",
        dest="command_name",
        default=None,
        help="Select one command from a multi-command source.",
    )
    commands_add_parser.add_argument(
        "--list",
        action="store_true",
        help="List remote candidate commands without installing anything.",
    )
    commands_add_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing local project command install.",
    )

    agents_parser = add_command_parser(
        "agents", "List or install project-scoped sub-agents."
    )
    agents_subparsers = agents_parser.add_subparsers(
        dest="agents_action",
        required=True,
        metavar="<action>",
    )
    agents_subparsers.add_parser(
        "list",
        prog="pbi-agent agents list",
        description="List installed project agents from .agents/agents.",
        help="List installed project agents.",
        formatter_class=CleanHelpFormatter,
    )
    agents_add_parser = agents_subparsers.add_parser(
        "add",
        prog="pbi-agent agents add",
        description=(
            "Install a project agent from the official catalog, a local path, "
            "or a GitHub repository."
        ),
        help="Install a project agent.",
        formatter_class=CleanHelpFormatter,
    )
    agents_add_parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help=(
            "Optional source. Omit to use the official pbi-agent/agents "
            "catalog. Supports local paths, owner/repo, repository URLs, and "
            "tree URLs."
        ),
    )
    agents_add_parser.add_argument(
        "--agent",
        dest="agent_name",
        default=None,
        help="Select one agent from a multi-agent source.",
    )
    agents_add_parser.add_argument(
        "--list",
        action="store_true",
        help="List remote candidate agents without installing anything.",
    )
    agents_add_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing local project agent install.",
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
        choices=[
            AUTH_MODE_API_KEY,
            AUTH_MODE_CHATGPT_ACCOUNT,
            AUTH_MODE_COPILOT_ACCOUNT,
        ],
        default=None,
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
        choices=[
            AUTH_MODE_API_KEY,
            AUTH_MODE_CHATGPT_ACCOUNT,
            AUTH_MODE_COPILOT_ACCOUNT,
        ],
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
        default=None,
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

    providers_usage_limits = providers_actions.add_parser(
        "usage-limits",
        prog="pbi-agent config providers usage-limits",
        description="Show subscription usage limits for a provider.",
        help="Show provider usage limits.",
        formatter_class=CleanHelpFormatter,
    )
    providers_usage_limits.add_argument("provider_id", help="Provider ID.")

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
            help="Sub-agent model override; omit to use the profile main model.",
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
        target.add_argument("--compact-tail-turns", type=int, default=None)
        target.add_argument("--compact-preserve-recent-tokens", type=int, default=None)
        target.add_argument("--compact-tool-output-max-chars", type=int, default=None)

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
        description="Set the default saved model profile for CLI runs and the web UI.",
        help="Select the default model profile.",
        formatter_class=CleanHelpFormatter,
    )
    profiles_select.add_argument("profile_id", help="Model profile ID.")

    return parser


def _argv_with_default_command(  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint and exported for compatibility
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

        if token in command_names or token in {"-h", "--help", "-v", "--version"}:
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


def _web_runtime_flags_in_args(raw_argv: list[str]) -> list[str]:  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint and exported for compatibility
    runtime_flags = {
        "--provider",
        "--responses-url",
        "--api-key",
        "--openai-api-key",
        "--azure-api-key",
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
        "--compact-tail-turns",
        "--compact-preserve-recent-tokens",
        "--compact-tool-output-max-chars",
    }
    seen: list[str] = []
    for token in raw_argv:
        flag = token.split("=", 1)[0]
        if flag in runtime_flags:
            seen.append(flag)
    return seen
