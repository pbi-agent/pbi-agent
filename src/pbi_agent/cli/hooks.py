from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pbi_agent.config import Settings
from pbi_agent.hooks.discovery import discover_hooks
from pbi_agent.hooks.schemas import HookDefinition
from pbi_agent.hooks.trust import HookTrustStore


def _handle_hooks_command(  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint
    args: argparse.Namespace,
) -> int:
    workspace = Path(getattr(args, "project_dir", Path("."))).resolve()
    discovery = discover_hooks(workspace, Settings())
    hooks = list(discovery.hooks)
    if getattr(args, "json_output", False):
        print(
            json.dumps(
                {
                    "hooks": [_hook_payload(hook) for hook in hooks],
                    "diagnostics": list(discovery.diagnostics),
                },
                indent=2,
            )
        )
        return 0
    if not hooks:
        print("No hooks discovered.")
        return 0
    for hook in hooks:
        managed = " managed" if hook.managed else ""
        print(
            f"{hook.event.value} [{hook.trust_status.value}{managed}] "
            f"matcher={hook.matcher or '*'} source={hook.source}"
        )
        print(f"  command: {hook.handler.command}")
        print(f"  key: {hook.key}")
        print(f"  hash: {hook.current_hash}")
        if hook.handler.status_message:
            print(f"  status: {hook.handler.status_message}")
        print(f"  timeout: {hook.handler.normalized_timeout}s")
        for diagnostic in hook.diagnostics:
            print(f"  diagnostic: {diagnostic}")
    if discovery.diagnostics:
        print("\nDiagnostics:", file=sys.stderr)
        for diagnostic in discovery.diagnostics:
            print(f"- {diagnostic}", file=sys.stderr)
    print(
        "\nReview: use `pbi-agent hooks trust <hook-key>` after inspecting a hook, "
        "or manage hooks in the web Settings → Hooks browser."
    )
    return 0


def _handle_hooks_trust_command(  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint
    args: argparse.Namespace,
) -> int:
    hook = _find_hook(Path(args.project_dir).resolve(), args.hook_key)
    if hook is None:
        print(f"Error: hook not found: {args.hook_key}", file=sys.stderr)
        return 1
    if hook.managed:
        print("Managed hooks are trusted by policy; no action needed.")
        return 0
    HookTrustStore().trust(hook.key, hook.current_hash)
    print(f"Trusted hook: {hook.event.value} {hook.handler.command}")
    return 0


def _handle_hooks_enable_command(  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint
    args: argparse.Namespace, *, enabled: bool
) -> int:
    hook = _find_hook(Path(args.project_dir).resolve(), args.hook_key)
    if hook is None:
        print(f"Error: hook not found: {args.hook_key}", file=sys.stderr)
        return 1
    if hook.managed:
        print(
            "Error: managed hooks cannot be disabled or enabled manually.",
            file=sys.stderr,
        )
        return 2
    HookTrustStore().set_enabled(hook.key, enabled)
    action = "Enabled" if enabled else "Disabled"
    print(f"{action} hook: {hook.event.value} {hook.handler.command}")
    return 0


def _find_hook(workspace: Path, key: str) -> HookDefinition | None:
    for hook in discover_hooks(workspace, Settings()).hooks:
        if hook.key == key:
            return hook
    return None


def _hook_payload(hook: HookDefinition) -> dict[str, object]:
    return {
        "key": hook.key,
        "event": hook.event.value,
        "matcher": hook.matcher,
        "command": hook.handler.command,
        "source": hook.source,
        "source_path": str(hook.source_path),
        "status_message": hook.handler.status_message,
        "timeout": hook.handler.normalized_timeout,
        "trust_status": hook.trust_status.value,
        "current_hash": hook.current_hash,
        "enabled": hook.enabled,
        "managed": hook.managed,
        "diagnostics": list(hook.diagnostics),
        "runnable": hook.runnable,
    }
