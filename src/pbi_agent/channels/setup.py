from __future__ import annotations

from pathlib import Path

from pbi_agent.channels.manager import WorkspaceChannelManager, validate_telegram_config
from pbi_agent.channels.types import ChannelRuntimeStatus, TelegramChannelConfig
from pbi_agent.config import ConfigError, ResolvedRuntime, Settings, resolve_web_runtime
from pbi_agent.workspace_context import WorkspaceContext, current_workspace_context


def payload_string_list(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    return [str(item).strip() for item in value if str(item).strip()]


def parse_id_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items: list[str] = []
    for line in value.splitlines():
        for part in line.split(","):
            item = part.strip()
            if item:
                items.append(item)
    return items


def merge_telegram_channel_config(
    current: TelegramChannelConfig,
    payload: dict[str, object],
) -> TelegramChannelConfig:
    token_secret = payload.get("token_secret")
    raw_allowed_users = payload.get("allowed_users")
    raw_allowed_chats = payload.get("allowed_chats")
    config = TelegramChannelConfig(
        enabled=bool(payload.get("enabled")),
        token_source=str(payload.get("token_source") or current.token_source),
        token_env_var=str(payload.get("token_env_var") or current.token_env_var),
        token_secret=(
            str(token_secret)
            if isinstance(token_secret, str) and token_secret.strip()
            else current.token_secret
        ),
        allowed_users=payload_string_list(raw_allowed_users, current.allowed_users),
        allowed_chats=payload_string_list(raw_allowed_chats, current.allowed_chats),
        last_update_id=current.last_update_id,
    )
    if config.token_source not in {"env", "secret"}:
        config.token_source = "env"
    return config


def telegram_channel_view(
    config: TelegramChannelConfig,
    status: ChannelRuntimeStatus,
) -> dict[str, object]:
    return {
        "enabled": config.enabled,
        "token_source": config.token_source,
        "token_env_var": config.token_env_var,
        "has_token_secret": config.has_secret,
        "allowed_users": config.allowed_users,
        "allowed_chats": config.allowed_chats,
        "last_update_id": config.last_update_id,
        "status": {"state": status.state, "error": status.error},
    }


def channels_payload(manager: WorkspaceChannelManager) -> dict[str, object]:
    config = manager.telegram_config()
    status = manager.status()
    return {"telegram": telegram_channel_view(config, status)}


def resolve_channel_runtime() -> ResolvedRuntime:
    try:
        return resolve_web_runtime()
    except ConfigError:
        return ResolvedRuntime(
            settings=Settings(api_key="", provider="openai", model="gpt-5.4"),
            provider_id=None,
            profile_id=None,
        )


def channel_manager_for_workspace(
    workspace_context: WorkspaceContext | None = None,
) -> WorkspaceChannelManager:
    workspace_context = workspace_context or current_workspace_context()
    runtime = resolve_channel_runtime()
    return WorkspaceChannelManager(
        runtime=runtime,
        workspace_root=Path(workspace_context.execution_root),
        directory_key=workspace_context.directory_key,
        owner_id="cli",
    )


def build_telegram_update_payload(
    current: TelegramChannelConfig,
    *,
    enabled: bool | None = None,
    token_source: str | None = None,
    token_env_var: str | None = None,
    token_secret: str | None = None,
    allowed_users: list[str] | None = None,
    allowed_chats: list[str] | None = None,
    clear_token_secret: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": current.enabled if enabled is None else enabled,
        "token_source": token_source or current.token_source,
        "token_env_var": token_env_var or current.token_env_var,
        "allowed_users": current.allowed_users
        if allowed_users is None
        else allowed_users,
        "allowed_chats": current.allowed_chats
        if allowed_chats is None
        else allowed_chats,
    }
    if clear_token_secret:
        payload["token_secret"] = ""
    elif token_secret is not None:
        payload["token_secret"] = token_secret
    return payload


def apply_telegram_channel_update(
    manager: WorkspaceChannelManager,
    payload: dict[str, object],
    *,
    restart_runner: bool,
) -> dict[str, object]:
    current = manager.telegram_config()
    config = merge_telegram_channel_config(current, payload)
    token_secret_value = payload.get("token_secret")
    if isinstance(token_secret_value, str) and not token_secret_value.strip():
        config.token_secret = None
    if restart_runner:
        manager.update_telegram_config(config)
    else:
        manager.persist_telegram_config(config)
    return channels_payload(manager)


def configured_status_for_config(
    config: TelegramChannelConfig,
) -> ChannelRuntimeStatus:
    return validate_telegram_config(config)
