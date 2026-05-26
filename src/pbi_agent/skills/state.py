from __future__ import annotations

from pathlib import Path

from pbi_agent.session_store import SessionStore
from pbi_agent.workspace_context import resolve_workspace_context


def workspace_key_for_skills(
    workspace: Path | None = None,
    *,
    directory_key: str | None = None,
) -> str:
    if directory_key is not None and directory_key.strip():
        return directory_key
    return resolve_workspace_context(cwd=workspace).directory_key


def is_skill_enabled(
    name: str,
    *,
    workspace: Path | None = None,
    directory_key: str | None = None,
) -> bool:
    disabled = _disabled_names(
        workspace_key_for_skills(workspace, directory_key=directory_key)
    )
    return name.casefold() not in disabled


def skill_enabled_map(
    names: list[str],
    *,
    workspace: Path | None = None,
    directory_key: str | None = None,
) -> dict[str, bool]:
    disabled = _disabled_names(
        workspace_key_for_skills(workspace, directory_key=directory_key)
    )
    return {name: name.casefold() not in disabled for name in names}


def set_skill_enabled(
    name: str,
    enabled: bool,
    *,
    workspace: Path | None = None,
    directory_key: str | None = None,
) -> None:
    with SessionStore() as store:
        store.set_project_skill_enabled(
            workspace_key_for_skills(workspace, directory_key=directory_key),
            name,
            enabled=enabled,
        )


def set_all_skills_enabled(
    names: list[str],
    enabled: bool,
    *,
    workspace: Path | None = None,
    directory_key: str | None = None,
) -> None:
    with SessionStore() as store:
        store.set_project_skills_enabled(
            workspace_key_for_skills(workspace, directory_key=directory_key),
            names,
            enabled=enabled,
        )


def _disabled_names(workspace_key: str) -> set[str]:
    try:
        with SessionStore() as store:
            return {
                name.casefold()
                for name in store.list_disabled_project_skills(workspace_key)
            }
    except Exception:  # noqa: BLE001 - skill state should not block prompt assembly
        return set()
