from __future__ import annotations

from typing import Any

from pbi_agent.tools.types import ToolHandler, ToolSpec

_REGISTRY: dict[str, tuple[ToolSpec, ToolHandler]] = {}

# --- built-in function tools -----------------------------------------------
from pbi_agent.tools.skill_knowledge import SPEC as _sk_spec, handle as _sk_handle  # noqa: E402
from pbi_agent.tools.init_report import SPEC as _ir_spec, handle as _ir_handle  # noqa: E402
from pbi_agent.tools.shell import SPEC as _sh_spec, handle as _sh_handle  # noqa: E402
from pbi_agent.tools.python_exec import SPEC as _pe_spec, handle as _pe_handle  # noqa: E402
from pbi_agent.tools.apply_patch import SPEC as _ap_spec, handle as _ap_handle  # noqa: E402
from pbi_agent.tools.find_files import SPEC as _ff_spec, handle as _ff_handle  # noqa: E402
from pbi_agent.tools.list_files import SPEC as _lf_spec, handle as _lf_handle  # noqa: E402
from pbi_agent.tools.search_files import SPEC as _sf_spec, handle as _sf_handle  # noqa: E402
from pbi_agent.tools.read_file import SPEC as _rf_spec, handle as _rf_handle  # noqa: E402
from pbi_agent.tools.sub_agent import SPEC as _sa_spec, handle as _sa_handle  # noqa: E402

_REGISTRY[_sk_spec.name] = (_sk_spec, _sk_handle)
_REGISTRY[_ir_spec.name] = (_ir_spec, _ir_handle)
_REGISTRY[_sh_spec.name] = (_sh_spec, _sh_handle)
_REGISTRY[_pe_spec.name] = (_pe_spec, _pe_handle)
_REGISTRY[_ap_spec.name] = (_ap_spec, _ap_handle)
_REGISTRY[_ff_spec.name] = (_ff_spec, _ff_handle)
_REGISTRY[_lf_spec.name] = (_lf_spec, _lf_handle)
_REGISTRY[_sf_spec.name] = (_sf_spec, _sf_handle)
_REGISTRY[_rf_spec.name] = (_rf_spec, _rf_handle)
_REGISTRY[_sa_spec.name] = (_sa_spec, _sa_handle)


def get_tool_specs(*, excluded_names: set[str] | None = None) -> list[ToolSpec]:
    excluded = excluded_names or set()
    return [item[0] for name, item in _REGISTRY.items() if name not in excluded]


def get_tool_handler(name: str) -> ToolHandler | None:
    entry = _REGISTRY.get(name)
    if entry is None:
        return None
    return entry[1]


def get_tool_spec(name: str) -> ToolSpec | None:
    entry = _REGISTRY.get(name)
    if entry is None:
        return None
    return entry[0]


def get_openai_tool_definitions(
    *, excluded_names: set[str] | None = None
) -> list[dict[str, Any]]:
    """Return tool definitions in OpenAI Responses API format.

    All tools are now registered function tools — no provider-specific
    native types.
    """
    tools: list[dict[str, Any]] = []
    for spec in get_tool_specs(excluded_names=excluded_names):
        tools.append(
            {
                "type": "function",
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters_schema,
            }
        )
    return tools


def get_anthropic_tool_definitions(
    *, excluded_names: set[str] | None = None
) -> list[dict[str, Any]]:
    """Return tool definitions in Anthropic Messages API format.

    All tools are now registered function tools — no provider-specific
    native types.
    """
    tools: list[dict[str, Any]] = []
    for spec in get_tool_specs(excluded_names=excluded_names):
        tools.append(
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.parameters_schema,
            }
        )
    return tools


def get_openai_chat_tool_definitions(
    *, excluded_names: set[str] | None = None
) -> list[dict[str, Any]]:
    """Return tool definitions in OpenAI Chat Completions format."""
    tools: list[dict[str, Any]] = []
    for spec in get_tool_specs(excluded_names=excluded_names):
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters_schema,
                },
            }
        )
    return tools
