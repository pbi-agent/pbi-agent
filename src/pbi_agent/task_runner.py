from __future__ import annotations

from pathlib import Path

from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.display.protocol import DisplayProtocol


def run_single_turn_in_directory(
    prompt: str,
    settings: Settings | ResolvedRuntime,
    display: DisplayProtocol,
    *,
    project_dir: str | Path = ".",
    workspace_root: Path | None = None,
    single_turn_hint: str | None = None,
    resume_session_id: str | None = None,
    image_paths: list[str] | None = None,
    persisted_user_message_id: int | None = None,
):
    from pbi_agent.agent.session import run_single_turn

    root = (workspace_root or Path.cwd()).resolve()
    target = (root / Path(project_dir)).resolve()
    target.relative_to(root)
    if not target.exists():
        raise FileNotFoundError(f"Project directory does not exist: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {target}")

    hint_parts: list[str] = []
    if single_turn_hint:
        hint_parts.append(single_turn_hint)
    normalized_project_dir = (
        str(project_dir).strip() if str(project_dir).strip() else "."
    )
    if normalized_project_dir not in {"", "."}:
        hint_parts.append(
            "Workspace focus: prefer files and commands under "
            f"`{normalized_project_dir}` unless the task explicitly requires "
            "changes elsewhere in the workspace."
        )
    resolved_hint = " ".join(hint_parts) if hint_parts else None

    return run_single_turn(
        prompt,
        settings,
        display,
        single_turn_hint=resolved_hint,
        resume_session_id=resume_session_id,
        image_paths=image_paths,
        persisted_user_message_id=persisted_user_message_id,
    )
