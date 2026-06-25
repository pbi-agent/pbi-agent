from __future__ import annotations

import os
from pathlib import Path

from pbi_agent.channels.telegram import TELEGRAM_PLATFORM, TelegramChannelRunner
from pbi_agent.channels.types import ChannelRuntimeStatus, TelegramChannelConfig
from pbi_agent.config import ResolvedRuntime
from pbi_agent.session_store import SessionStore


class WorkspaceChannelManager:
    def __init__(
        self,
        *,
        runtime: ResolvedRuntime,
        workspace_root: Path,
        directory_key: str,
        owner_id: str,
    ) -> None:
        self._runtime = runtime
        self._workspace_root = workspace_root
        self._directory_key = directory_key
        self._owner_id = owner_id
        self._telegram_runner: TelegramChannelRunner | None = None

    def start_enabled(self) -> None:
        config = self.telegram_config()
        if not config.enabled:
            self._set_status(ChannelRuntimeStatus("disabled"))
            return
        status = validate_telegram_config(config)
        if status.state == "error":
            self._set_status(status)
            return
        self._telegram_runner = TelegramChannelRunner(
            runtime=self._runtime,
            workspace_root=self._workspace_root,
            directory_key=self._directory_key,
            config=config,
            owner_id=self._owner_id,
        )
        self._telegram_runner.start()

    def stop(self) -> None:
        if self._telegram_runner is not None:
            self._telegram_runner.stop()
            self._telegram_runner = None

    def restart(self) -> ChannelRuntimeStatus:
        self.stop()
        self.start_enabled()
        return self.status()

    def status(self) -> ChannelRuntimeStatus:
        if self._telegram_runner is not None:
            return self._telegram_runner.status
        record = self._record()
        if record is None:
            return ChannelRuntimeStatus("disabled")
        return ChannelRuntimeStatus(record.status, record.error)

    def telegram_config(self) -> TelegramChannelConfig:
        record = self._record()
        return TelegramChannelConfig.from_dict(record.config if record else None)

    def persist_telegram_config(
        self,
        config: TelegramChannelConfig,
    ) -> ChannelRuntimeStatus:
        status = validate_telegram_config(config)
        with SessionStore() as store:
            store.set_channel_config(
                self._directory_key,
                TELEGRAM_PLATFORM,
                config.to_storage_dict(),
                status=status.state if config.enabled else "disabled",
                error=status.error,
            )
        return status

    def update_telegram_config(
        self,
        config: TelegramChannelConfig,
    ) -> ChannelRuntimeStatus:
        self.persist_telegram_config(config)
        self.restart()
        return self.status()

    def _record(self):
        with SessionStore() as store:
            return store.get_channel_config(self._directory_key, TELEGRAM_PLATFORM)

    def _set_status(self, status: ChannelRuntimeStatus) -> None:
        with SessionStore() as store:
            store.set_channel_status(
                self._directory_key,
                TELEGRAM_PLATFORM,
                status=status.state,
                error=status.error,
            )


def validate_telegram_config(config: TelegramChannelConfig) -> ChannelRuntimeStatus:
    if not config.enabled:
        return ChannelRuntimeStatus("disabled")
    if config.token_source == "secret":
        has_token = bool(config.token_secret)
    else:
        has_token = bool(config.token_env_var.strip()) and bool(
            os.environ.get(config.token_env_var, "").strip()
        )
    if not has_token:
        return ChannelRuntimeStatus("error", "Telegram bot token source is required.")
    if not config.has_allowlist:
        return ChannelRuntimeStatus(
            "error",
            "Add at least one allowed Telegram user or chat/channel ID.",
        )
    return ChannelRuntimeStatus("configured")
