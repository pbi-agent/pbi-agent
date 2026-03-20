from __future__ import annotations

import sys
from pathlib import Path

SYSTEM_PROMPT = """
You are pbi-agent, a local CLI coding agent for creating, auditing, and editing Power BI PBIP projects.

<environment>
- You run locally with workspace read/write access through function tools.
</environment>

<power_bi_rules>
- Always use explicit Power BI measures for displayed values in visuals; do not rely on implicit aggregations.
- Never create or rename a table to `Measures`; use `_Measures` for a dedicated measures table.
- Never modify auto-generated date tables whose names start with `DateTableTemplate_` or `LocalDateTable_`.
- When adding descriptions, skip those auto-generated date tables because their restricted TMDL schema does not support normal metadata edits.
- When laying out visuals, distribute them intentionally across the canvas and avoid clustering them into one area unless the user asked for that layout.
- If the user does not specify styling, apply the default preset for the visual type from the skill knowledge base.
- Style priority is: explicit user instruction > existing project or brand conventions > skill default preset.
</power_bi_rules>
""".strip()

_SUB_AGENT_PROMPT = """
<persona>
- You are a delegated sub-agent operating on behalf of the main agent.
- You are in background mode and will not interact with the user directly. Do not ask the user questions.
</persona>
""".strip()

SUB_AGENT_SYSTEM_PROMPT = f"{SYSTEM_PROMPT}\n\n{_SUB_AGENT_PROMPT}"

_MAX_PROJECT_RULES_BYTES = 1_000_000  # 1 MB


def _warn_project_rules(message: str) -> None:
    print(message, file=sys.stderr)


def load_project_rules(cwd: Path | None = None) -> str | None:
    """Read an optional ``AGENTS.md`` file from *cwd* (default: CWD).

    Returns the file content, or ``None`` when the file is absent, empty,
    or unreadable.
    """
    target = (cwd or Path.cwd()) / "AGENTS.md"

    try:
        size = target.stat().st_size
    except FileNotFoundError:
        return None
    except OSError:
        _warn_project_rules("AGENTS.md found but unreadable due to permissions.")
        return None

    if size > _MAX_PROJECT_RULES_BYTES:
        _warn_project_rules("AGENTS.md exceeds 1 MB; content will be truncated.")

    try:
        with target.open("rb") as fh:
            raw_content = fh.read(_MAX_PROJECT_RULES_BYTES)
    except OSError:
        _warn_project_rules("AGENTS.md found but unreadable due to permissions.")
        return None

    content = raw_content.decode("utf-8", errors="replace").strip()
    if not content:
        return None

    return content


def _append_project_rules(base_prompt: str) -> str:
    """Append ``<project_rules>`` section if ``AGENTS.md`` is present."""
    rules = load_project_rules()
    if rules is None:
        return base_prompt
    return f"{base_prompt}\n\n<project_rules>\n{rules}\n</project_rules>"


def get_system_prompt() -> str:
    return _append_project_rules(SYSTEM_PROMPT)


def get_sub_agent_system_prompt() -> str:
    return _append_project_rules(SUB_AGENT_SYSTEM_PROMPT)
