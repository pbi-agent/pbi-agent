"""skill_knowledge tool — retrieves Power BI skill definitions from the knowledge base."""

from __future__ import annotations

from typing import Any

from pbi_agent.skills import list_available_skills, load_skill
from pbi_agent.tools.types import ToolContext, ToolSpec


def build_spec() -> ToolSpec:
    """Build the ToolSpec dynamically from available skill files."""
    available = list_available_skills()
    skill_names = [name for name, _ in available]

    catalog_lines = [f"- {name}: {brief}" for name, brief in available]
    catalog = "\n".join(catalog_lines)

    description = (
        "Get Power BI skill definitions. MUST be called before creating or "
        f"editing a visual.\n\nAvailable skills:\n{catalog}"
    )

    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "skills": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": skill_names,
                },
                "description": "List of skill names to retrieve.",
            },
        },
        "required": ["skills"],
        "additionalProperties": False,
    }

    return ToolSpec(
        name="skill_knowledge",
        description=description,
        parameters_schema=parameters_schema,
        is_destructive=False,
    )


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Load and return the requested skill definitions."""
    requested: list[str] = arguments.get("skills", [])
    if not requested:
        return {"error": "No skill names provided."}

    results: dict[str, str] = {}
    errors: list[str] = []

    for name in requested:
        content = load_skill(name)
        if content is None:
            available = [s for s, _ in list_available_skills()]
            errors.append(f"Skill '{name}' not found. Available: {available}")
        else:
            results[name] = content

    response: dict[str, Any] = {"skills": results}
    if errors:
        response["errors"] = errors
    return response


SPEC = build_spec()
