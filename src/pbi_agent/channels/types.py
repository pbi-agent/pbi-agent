from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ChannelRuntimeStatus:
    state: str = "disabled"
    error: str | None = None


@dataclass(slots=True)
class TelegramChannelConfig:
    enabled: bool = False
    token_source: str = "env"
    token_env_var: str = "PBI_AGENT_TELEGRAM_BOT_TOKEN"
    token_secret: str | None = None
    allowed_users: list[str] = field(default_factory=list)
    allowed_chats: list[str] = field(default_factory=list)
    last_update_id: int | None = None

    @property
    def has_secret(self) -> bool:
        return bool(self.token_secret)

    @property
    def has_allowlist(self) -> bool:
        return bool(self.allowed_users or self.allowed_chats)

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> "TelegramChannelConfig":
        if not payload:
            return cls()
        token_source = str(payload.get("token_source") or "env")
        if token_source not in {"env", "secret"}:
            token_source = "env"
        return cls(
            enabled=bool(payload.get("enabled")),
            token_source=token_source,
            token_env_var=str(
                payload.get("token_env_var") or "PBI_AGENT_TELEGRAM_BOT_TOKEN"
            ),
            token_secret=(
                str(payload["token_secret"])
                if isinstance(payload.get("token_secret"), str)
                and payload.get("token_secret")
                else None
            ),
            allowed_users=_string_list(payload.get("allowed_users")),
            allowed_chats=_string_list(payload.get("allowed_chats")),
            last_update_id=_optional_int(payload.get("last_update_id")),
        )

    def to_storage_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "token_source": self.token_source,
            "token_env_var": self.token_env_var,
            "token_secret": self.token_secret,
            "allowed_users": self.allowed_users,
            "allowed_chats": self.allowed_chats,
            "last_update_id": self.last_update_id,
        }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None
