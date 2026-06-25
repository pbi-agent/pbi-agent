from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any
from urllib import error, request

from pbi_agent.channels.setup import (
    apply_telegram_channel_update,
    build_telegram_update_payload,
    channel_manager_for_workspace,
    channels_payload,
    parse_id_list,
)
from pbi_agent.web.defaults import DEFAULT_WEB_PORT
from pbi_agent.workspace_context import current_workspace_context

CommandParserFactory = Callable[[str, str], argparse.ArgumentParser]


def add_channels_parser(
    add_command_parser: CommandParserFactory,
    *,
    formatter_class: type[argparse.HelpFormatter],
) -> argparse.ArgumentParser:
    channels_parser = add_command_parser(
        "channels",
        "Show and configure workspace messaging channels.",
    )
    channels_subparsers = channels_parser.add_subparsers(
        dest="channels_action",
        required=True,
        metavar="<action>",
    )
    channels_show_parser = channels_subparsers.add_parser(
        "show",
        prog="pbi-agent channels show",
        description="Show configured channels for the current workspace.",
        help="Show configured channels.",
        formatter_class=formatter_class,
    )
    channels_show_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable JSON instead of a summary.",
    )
    channels_telegram_parser = channels_subparsers.add_parser(
        "telegram",
        prog="pbi-agent channels telegram",
        description="Configure the Telegram channel for the current workspace.",
        help="Configure the Telegram channel.",
        formatter_class=formatter_class,
    )
    channels_telegram_subparsers = channels_telegram_parser.add_subparsers(
        dest="telegram_action",
        required=True,
        metavar="<action>",
    )
    channels_telegram_show_parser = channels_telegram_subparsers.add_parser(
        "show",
        prog="pbi-agent channels telegram show",
        description="Show Telegram channel settings for the current workspace.",
        help="Show Telegram channel settings.",
        formatter_class=formatter_class,
    )
    channels_telegram_show_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable JSON instead of a summary.",
    )
    channels_telegram_configure_parser = channels_telegram_subparsers.add_parser(
        "configure",
        prog="pbi-agent channels telegram configure",
        description="Update Telegram channel settings for the current workspace.",
        help="Update Telegram channel settings.",
        formatter_class=formatter_class,
    )
    channels_telegram_configure_parser.add_argument(
        "--enable",
        action="store_true",
        help="Enable the Telegram channel.",
    )
    channels_telegram_configure_parser.add_argument(
        "--disable",
        action="store_true",
        help="Disable the Telegram channel.",
    )
    channels_telegram_configure_parser.add_argument(
        "--token-source",
        choices=("env", "secret"),
        default=None,
        help="Read the bot token from an environment variable or stored secret.",
    )
    channels_telegram_configure_parser.add_argument(
        "--token-env-var",
        default=None,
        help="Environment variable name when --token-source env is used.",
    )
    channels_telegram_configure_parser.add_argument(
        "--token-secret",
        default=None,
        help="Stored bot token when --token-source secret is used.",
    )
    channels_telegram_configure_parser.add_argument(
        "--clear-token-secret",
        action="store_true",
        help="Remove a stored bot token secret.",
    )
    channels_telegram_configure_parser.add_argument(
        "--allowed-users",
        default=None,
        help="Allowed Telegram user IDs (comma- or newline-separated).",
    )
    channels_telegram_configure_parser.add_argument(
        "--allowed-chats",
        default=None,
        help="Allowed Telegram chat/channel IDs (comma- or newline-separated).",
    )
    channels_telegram_configure_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable JSON instead of a summary.",
    )
    channels_telegram_restart_parser = channels_telegram_subparsers.add_parser(
        "restart",
        prog="pbi-agent channels telegram restart",
        description="Restart the Telegram channel runner for the current workspace.",
        help="Restart the Telegram channel runner.",
        formatter_class=formatter_class,
    )
    channels_telegram_restart_parser.add_argument(
        "--web-port",
        type=int,
        default=DEFAULT_WEB_PORT,
        help=f"Local web UI port for restart requests (default: {DEFAULT_WEB_PORT}).",
    )
    channels_telegram_restart_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable JSON instead of a summary.",
    )
    return channels_parser


def _handle_channels_command(args: argparse.Namespace) -> int:  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint
    if args.channels_action == "show":
        return _handle_channels_show_command(args)
    if args.channels_action == "telegram":
        return _handle_channels_telegram_command(args)
    print(f"Error: unknown channels action {args.channels_action!r}", file=sys.stderr)
    return 2


def _handle_channels_show_command(args: argparse.Namespace) -> int:
    manager = channel_manager_for_workspace()
    payload = channels_payload(manager)
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    _print_channels_payload(payload)
    return 0


def _handle_channels_telegram_command(args: argparse.Namespace) -> int:
    telegram_action = getattr(args, "telegram_action", None)
    if telegram_action == "show":
        return _handle_channels_show_command(args)
    if telegram_action == "configure":
        return _handle_channels_telegram_configure_command(args)
    if telegram_action == "restart":
        return _handle_channels_telegram_restart_command(args)
    print(
        f"Error: unknown telegram channels action {telegram_action!r}",
        file=sys.stderr,
    )
    return 2


def _handle_channels_telegram_configure_command(args: argparse.Namespace) -> int:
    if args.enable and args.disable:
        print("Error: use only one of --enable or --disable.", file=sys.stderr)
        return 2
    if args.token_source is not None and args.token_source not in {"env", "secret"}:
        print("Error: --token-source must be 'env' or 'secret'.", file=sys.stderr)
        return 2

    manager = channel_manager_for_workspace()
    current = manager.telegram_config()
    enabled: bool | None
    if args.enable:
        enabled = True
    elif args.disable:
        enabled = False
    else:
        enabled = None

    payload = build_telegram_update_payload(
        current,
        enabled=enabled,
        token_source=args.token_source,
        token_env_var=args.token_env_var,
        token_secret=args.token_secret,
        allowed_users=parse_id_list(args.allowed_users),
        allowed_chats=parse_id_list(args.allowed_chats),
        clear_token_secret=bool(args.clear_token_secret),
    )
    if not _configure_options_specified(args):
        print(
            "Error: specify at least one configuration option.",
            file=sys.stderr,
        )
        return 2

    result = apply_telegram_channel_update(
        manager,
        payload,
        restart_runner=False,
    )
    if args.json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print("Updated Telegram channel configuration for the current workspace.")
    telegram = result.get("telegram")
    if isinstance(telegram, dict):
        _print_telegram_channel(telegram)
    print(
        "Restart the web UI or use "
        "`pbi-agent channels telegram restart` to apply changes to a running server.",
    )
    return 0


def _handle_channels_telegram_restart_command(args: argparse.Namespace) -> int:
    port = int(args.web_port)
    workspace_context = current_workspace_context()
    restarted_payload = _request_web_telegram_restart(
        port,
        workspace_context.directory_key,
    )
    if restarted_payload is not None:
        if args.json_output:
            print(json.dumps(restarted_payload, indent=2, sort_keys=True))
            return 0
        print("Restarted Telegram channel via the local web UI.")
        telegram = restarted_payload.get("telegram")
        if isinstance(telegram, dict):
            _print_telegram_channel(telegram)
        return 0

    manager = channel_manager_for_workspace(workspace_context)
    manager.persist_telegram_config(manager.telegram_config())
    payload = channels_payload(manager)
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(
        "No local web UI responded on "
        f"http://127.0.0.1:{port}/api/channels/telegram/restart."
    )
    print("Validated stored Telegram channel settings for the current workspace.")
    telegram = payload.get("telegram")
    if isinstance(telegram, dict):
        _print_telegram_channel(telegram)
    print(
        "Start or restart `pbi-agent web` for this workspace to run the Telegram channel."
    )
    return 0


def _configure_options_specified(args: argparse.Namespace) -> bool:
    return any(
        [
            args.enable,
            args.disable,
            args.token_source is not None,
            args.token_env_var is not None,
            args.token_secret is not None,
            args.clear_token_secret,
            args.allowed_users is not None,
            args.allowed_chats is not None,
        ]
    )


def _request_web_telegram_restart(
    port: int,
    expected_directory_key: str,
) -> dict[str, Any] | None:
    base_url = f"http://127.0.0.1:{port}"
    bootstrap = _request_web_json(f"{base_url}/api/bootstrap", method="GET")
    if not _web_workspace_matches(bootstrap, expected_directory_key):
        return None
    payload = _request_web_json(
        f"{base_url}/api/channels/telegram/restart",
        method="POST",
        data=b"",
    )
    if not isinstance(payload, dict) or "telegram" not in payload:
        return None
    return payload


def _request_web_json(
    url: str,
    *,
    method: str,
    data: bytes | None = None,
) -> dict[str, Any] | None:
    http_request = request.Request(url, method=method, data=data)
    try:
        with request.urlopen(http_request, timeout=3) as response:
            body = response.read().decode("utf-8")
    except (OSError, error.URLError, TimeoutError, UnicodeDecodeError):
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _web_workspace_matches(
    payload: dict[str, Any] | None,
    expected_directory_key: str,
) -> bool:
    if payload is None:
        return False
    workspace_key = payload.get("workspace_key")
    return (
        isinstance(workspace_key, str)
        and workspace_key.strip().lower() == expected_directory_key
    )


def _print_channels_payload(payload: dict[str, object]) -> None:
    telegram = payload.get("telegram")
    if not isinstance(telegram, dict):
        print("No channel configuration found.")
        return
    print("Channels for the current workspace:")
    _print_telegram_channel(telegram)


def _print_telegram_channel(telegram: dict[str, object]) -> None:
    status = telegram.get("status")
    state = "unknown"
    error_message = None
    if isinstance(status, dict):
        state = str(status.get("state") or "unknown")
        raw_error = status.get("error")
        error_message = str(raw_error) if raw_error else None

    print("Telegram")
    print(f"  enabled: {telegram.get('enabled')}")
    print(f"  status: {state}")
    if error_message:
        print(f"  error: {error_message}")
    print(f"  token_source: {telegram.get('token_source')}")
    print(f"  token_env_var: {telegram.get('token_env_var')}")
    print(f"  has_token_secret: {telegram.get('has_token_secret')}")
    print(f"  allowed_users: {telegram.get('allowed_users')}")
    print(f"  allowed_chats: {telegram.get('allowed_chats')}")
