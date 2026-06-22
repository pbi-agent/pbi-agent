from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pbi_agent.config import Settings
from pbi_agent.hooks.discovery import discover_hooks
from pbi_agent.hooks.schemas import HookDefinition, HookDiscovery, HookTrustStatus
from pbi_agent.hooks.trust import HookTrustStore

REVIEW_STATUSES = {HookTrustStatus.UNTRUSTED, HookTrustStatus.MODIFIED}


def hooks_requiring_review(discovery: HookDiscovery) -> list[HookDefinition]:
    return [hook for hook in discovery.hooks if hook.trust_status in REVIEW_STATUSES]


def discover_hooks_for_review(
    workspace: Path,
    settings: Settings | None = None,
) -> HookDiscovery:
    return discover_hooks(workspace, settings)


def format_hook_warning(hooks: Iterable[HookDefinition]) -> str | None:
    review_hooks = list(hooks)
    if not review_hooks:
        return None
    count = len(review_hooks)
    plural = "s" if count != 1 else ""
    return (
        f"{count} command hook{plural} require trust review and will be skipped. "
        "Run `pbi-agent hooks` or open Settings → Hooks."
    )


def format_hooks_markdown(discovery: HookDiscovery) -> str:
    lines = ["### Hooks"]
    if not discovery.hooks:
        lines.append("")
        lines.append("No command hooks discovered.")
    else:
        lines.append("")
        for hook in discovery.hooks:
            managed = ", managed" if hook.managed else ""
            lines.append(
                "- "
                f"`{hook.event.value}` matcher `{hook.matcher or '*'}` "
                f"from `{hook.source}` — **{hook.trust_status.value}**{managed}"
            )
            lines.append(f"  - command: `{hook.handler.command}`")
            lines.append(f"  - key: `{hook.key}`")
            if hook.handler.status_message:
                lines.append(f"  - status: {hook.handler.status_message}")
            for diagnostic in hook.diagnostics:
                lines.append(f"  - diagnostic: {diagnostic}")
    if discovery.diagnostics:
        lines.append("")
        lines.append("Diagnostics:")
        for diagnostic in discovery.diagnostics:
            lines.append(f"- {diagnostic}")
    lines.append("")
    lines.append(
        "Review hooks with `pbi-agent hooks` / `pbi-agent hooks trust <hook-key>` "
        "or open Settings → Hooks."
    )
    return "\n".join(lines)


def trust_hook(key: str, current_hash: str) -> None:
    HookTrustStore().trust(key, current_hash)


def set_hook_enabled(key: str, enabled: bool) -> None:
    HookTrustStore().set_enabled(key, enabled)
