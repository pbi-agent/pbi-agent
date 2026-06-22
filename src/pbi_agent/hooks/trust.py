from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pbi_agent.hooks.schemas import HookHandlerConfig, HookTrustStatus


DEFAULT_HOOK_STATE_PATH = Path.home() / ".pbi-agent" / "hooks_state.json"


@dataclass(frozen=True, slots=True)
class HookIdentitySlot:
    source: str
    source_path: str
    event: str
    matcher: str
    handler_identity: str
    occurrence: int
    single_handler_group: bool = False

    @property
    def key(self) -> str:
        return ":".join(
            (
                self.source,
                self.source_path,
                self.event,
                self.matcher,
                self.handler_identity,
                str(self.occurrence),
            )
        )

    @property
    def modified_fallback_prefix(self) -> str | None:
        if not self.single_handler_group:
            return None
        return ":".join(
            (
                self.source,
                self.source_path,
                self.event,
                self.matcher,
                "",
            )
        )


def normalized_hook_hash(
    *,
    event: str,
    matcher: str | None,
    handler: HookHandlerConfig,
) -> str:
    payload = {
        "event": event,
        "matcher": (matcher or "").strip(),
        "handler": {
            "type": handler.type,
            "command": handler.command or "",
            "timeout": handler.normalized_timeout,
            "statusMessage": handler.status_message or "",
        },
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hook_key(*, event: str, matcher: str | None, handler: HookHandlerConfig) -> str:
    return normalized_hook_hash(event=event, matcher=matcher, handler=handler)


def handler_identity(handler: HookHandlerConfig) -> str:
    command = (handler.command or "").strip()
    return normalized_hook_hash(
        event="handler_identity",
        matcher=handler.type,
        handler=HookHandlerConfig(type=handler.type, command=command),
    )


def hook_identity_slot(
    *,
    source: str,
    source_path: Path,
    event: str,
    matcher: str | None,
    handler: HookHandlerConfig,
    occurrence: int,
    single_handler_group: bool,
) -> HookIdentitySlot:
    return HookIdentitySlot(
        source=source,
        source_path=str(source_path.resolve()),
        event=event,
        matcher=(matcher or "").strip(),
        handler_identity=handler_identity(handler),
        occurrence=occurrence,
        single_handler_group=single_handler_group,
    )


class HookTrustStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_HOOK_STATE_PATH
        self._state = self._load()

    def status_for(
        self,
        key: str,
        current_hash: str,
        *,
        modified_fallback_prefix: str | None = None,
    ) -> HookTrustStatus:
        return self._status_for_key(
            key,
            current_hash,
            modified_fallback_prefix=modified_fallback_prefix,
        )

    def status_for_identity(
        self,
        identity: HookIdentitySlot,
        current_hash: str,
    ) -> HookTrustStatus:
        return self._status_for_key(
            identity.key,
            current_hash,
            modified_fallback_prefix=identity.modified_fallback_prefix,
        )

    def _status_for_key(
        self,
        key: str,
        current_hash: str,
        *,
        modified_fallback_prefix: str | None,
    ) -> HookTrustStatus:
        entry = self._state.get(key)
        if not isinstance(entry, dict):
            entry = self._single_fallback_entry(modified_fallback_prefix)
            if entry is None:
                return HookTrustStatus.UNTRUSTED
            return self._status_for_entry(entry, current_hash)
        return self._status_for_entry(entry, current_hash)

    def _status_for_entry(
        self,
        entry: dict[str, Any],
        current_hash: str,
    ) -> HookTrustStatus:
        if entry.get("enabled") is False:
            return HookTrustStatus.DISABLED
        trusted_hash = entry.get("trusted_hash")
        if trusted_hash == current_hash:
            return HookTrustStatus.TRUSTED
        return HookTrustStatus.MODIFIED

    def _single_fallback_entry(self, prefix: str | None) -> dict[str, Any] | None:
        if prefix is None:
            return None
        matches = [
            entry
            for state_key, entry in self._state.items()
            if state_key.startswith(prefix) and isinstance(entry, dict)
        ]
        if len(matches) != 1:
            return None
        return matches[0]

    def trust(self, key: str, current_hash: str) -> None:
        self._state[key] = {"enabled": True, "trusted_hash": current_hash}
        self._save()

    def set_enabled(self, key: str, enabled: bool) -> None:
        entry = self._state.setdefault(key, {})
        entry["enabled"] = enabled
        self._save()

    def _load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception:
            return {}
        state = raw.get("state") if isinstance(raw, dict) else None
        return dict(state) if isinstance(state, dict) else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"state": self._state}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
