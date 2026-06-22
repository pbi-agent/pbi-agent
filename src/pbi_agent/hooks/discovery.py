from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pbi_agent.config import Settings
from pbi_agent.hooks.schemas import (
    HookDefinition,
    HookDiscovery,
    HookEventName,
    HookHandlerConfig,
)
from pbi_agent.hooks.trust import (
    HookTrustStore,
    handler_identity,
    hook_identity_slot,
    normalized_hook_hash,
)

GLOBAL_HOOK_CONFIG_PATH = Path.home() / ".pbi-agent" / "hooks.json"


def discover_hooks(
    workspace: Path,
    settings: Settings | None = None,
    *,
    global_config_path: Path | None = None,
    project_config_path: Path | None = None,
    trust_store: HookTrustStore | None = None,
) -> HookDiscovery:
    workspace = workspace.resolve()
    sources = (
        ("global", global_config_path or GLOBAL_HOOK_CONFIG_PATH),
        ("project", project_config_path or workspace / ".agents" / "hooks.json"),
    )
    diagnostics: list[str] = []
    definitions: list[HookDefinition] = []
    trust = trust_store or HookTrustStore()
    group_order = 0
    handler_order = 0
    identity_counts: dict[tuple[str, str, str, str, str], int] = {}
    for source_name, path in sources:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            diagnostics.append(f"{path}: failed to parse hooks config: {exc}")
            continue
        hooks_obj = raw.get("hooks") if isinstance(raw, dict) else None
        if not isinstance(hooks_obj, dict):
            diagnostics.append(f"{path}: expected top-level object with 'hooks'")
            continue
        for event_text, groups_raw in hooks_obj.items():
            try:
                event = HookEventName(event_text)
            except ValueError:
                diagnostics.append(f"{path}: unsupported hook event {event_text!r}")
                continue
            if not isinstance(groups_raw, list):
                diagnostics.append(f"{path}: event {event} must contain a list")
                continue
            for group_raw in groups_raw:
                group_order += 1
                if not isinstance(group_raw, dict):
                    diagnostics.append(f"{path}: hook group must be an object")
                    continue
                matcher = _optional_str(group_raw.get("matcher"))
                handlers_raw = group_raw.get("hooks")
                if not isinstance(handlers_raw, list):
                    diagnostics.append(f"{path}: hook group missing hooks list")
                    continue
                for handler_raw in handlers_raw:
                    handler_order += 1
                    handler, handler_diags = _parse_handler(handler_raw, path)
                    if handler is None:
                        diagnostics.extend(handler_diags)
                        continue
                    handler, managed_diagnostics = _apply_managed_source_policy(
                        handler,
                        source_name=source_name,
                        path=path,
                    )
                    handler_diags.extend(managed_diagnostics)
                    current_hash = normalized_hook_hash(
                        event=event.value,
                        matcher=matcher,
                        handler=handler,
                    )
                    identity_base = (
                        source_name,
                        str(path.resolve()),
                        event.value,
                        (matcher or "").strip(),
                        handler_identity(handler),
                    )
                    identity_counts[identity_base] = (
                        identity_counts.get(identity_base, 0) + 1
                    )
                    identity = hook_identity_slot(
                        source=source_name,
                        source_path=path,
                        event=event.value,
                        matcher=matcher,
                        handler=handler,
                        occurrence=identity_counts[identity_base],
                        single_handler_group=len(handlers_raw) == 1,
                    )
                    bypass_trust = bool(
                        getattr(settings, "dangerously_bypass_hook_trust", False)
                    )
                    definitions.append(
                        HookDefinition(
                            event=event,
                            matcher=matcher,
                            handler=handler,
                            source=source_name,
                            source_path=path,
                            order=handler_order,
                            group_order=group_order,
                            key=identity.key,
                            current_hash=current_hash,
                            trust_status=trust.status_for_identity(
                                identity,
                                current_hash,
                                managed=handler.managed,
                                bypass_trust=bypass_trust,
                            ),
                            diagnostics=tuple(handler_diags),
                            managed=handler.managed,
                        )
                    )
    return HookDiscovery(hooks=tuple(definitions), diagnostics=tuple(diagnostics))


def _parse_handler(
    raw: Any,
    path: Path,
) -> tuple[HookHandlerConfig | None, list[str]]:
    diagnostics: list[str] = []
    if not isinstance(raw, dict):
        return None, [f"{path}: hook handler must be an object"]
    type_ = str(raw.get("type") or "command")
    async_ = bool(raw.get("async", False))
    handler = HookHandlerConfig(
        type=type_,
        command=_optional_str(raw.get("command")),
        timeout=raw.get("timeout"),
        status_message=_optional_str(raw.get("statusMessage")),
        async_=async_,
        managed=bool(raw.get("managed", False)),
        raw=dict(raw),
    )
    if type_ != "command":
        diagnostics.append(f"{path}: skipping unsupported hook type {type_!r}")
        return None, diagnostics
    if async_:
        diagnostics.append(f"{path}: skipping async command hook")
        return None, diagnostics
    if not handler.command:
        diagnostics.append(f"{path}: command hook missing command")
        return None, diagnostics
    return handler, diagnostics


def _apply_managed_source_policy(
    handler: HookHandlerConfig,
    *,
    source_name: str,
    path: Path,
) -> tuple[HookHandlerConfig, list[str]]:
    """Apply the minimal safe policy for trusted-by-policy managed hooks.

    Ordinary global/project JSON is user- or workspace-controlled. Until a
    separate trusted managed source exists, self-declared ``managed`` in those
    files must not bypass hook trust review or disable controls.
    """

    if not handler.managed:
        return handler, []
    if source_name == "managed":
        return handler, []
    raw = dict(handler.raw)
    raw["managed"] = False
    return (
        HookHandlerConfig(
            type=handler.type,
            command=handler.command,
            timeout=handler.timeout,
            status_message=handler.status_message,
            async_=handler.async_,
            managed=False,
            raw=raw,
        ),
        [(f"{path}: ignoring self-declared managed hook from {source_name} source")],
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
