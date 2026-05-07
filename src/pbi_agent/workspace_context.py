from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


WORKSPACE_KEY_ENV = "PBI_AGENT_WORKSPACE_KEY"
WORKSPACE_DISPLAY_PATH_ENV = "PBI_AGENT_WORKSPACE_DISPLAY_PATH"
SANDBOX_ENV = "PBI_AGENT_SANDBOX"


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    execution_root: Path
    key: str
    directory_key: str
    display_path: str
    is_sandbox: bool


def resolve_workspace_context(
    *,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> WorkspaceContext:
    env = environ if environ is not None else os.environ
    execution_root = (cwd or Path.cwd()).resolve()
    fallback_key = str(execution_root)
    key = _non_empty_env(env, WORKSPACE_KEY_ENV) or fallback_key
    display_path = _non_empty_env(env, WORKSPACE_DISPLAY_PATH_ENV) or key
    is_sandbox = _truthy(_non_empty_env(env, SANDBOX_ENV))
    return WorkspaceContext(
        execution_root=execution_root,
        key=key,
        directory_key=key.lower(),
        display_path=display_path,
        is_sandbox=is_sandbox,
    )


def current_workspace_context() -> WorkspaceContext:
    return resolve_workspace_context(environ=os.environ)


def current_workspace_directory_key() -> str:
    return current_workspace_context().directory_key


def _non_empty_env(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() not in {"0", "false", "no", "off"}
