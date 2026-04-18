from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from typing import Any

from pbi_agent import __version__
from pbi_agent.auth.providers.openai_chatgpt import OPENAI_CHATGPT_RESPONSES_URL
from pbi_agent.agent.tool_runtime import to_function_call_output_items
from pbi_agent.models.messages import CompletedResponse
from pbi_agent.tools.types import ToolResult

CHATGPT_TURN_STATE_HEADER = "x-codex-turn-state"


@dataclass(frozen=True)
class ResponsesRequestOptions:
    include_max_output_tokens: bool = True
    store: bool = True
    include_prompt_cache_retention: bool = True
    include_context_management: bool = True
    stream: bool = False
    tool_choice: str | None = None
    include: list[str] | None = None
    use_session_prompt_cache_key: bool = False


def chatgpt_user_agent() -> str:
    return (
        f"opencode/{__version__} "
        f"({platform.system().lower()} {platform.release()}; {platform.machine().lower()})"
    )


class ChatGPTCodexBackend:
    def __init__(self, *, responses_url: str) -> None:
        self._enabled = responses_url == OPENAI_CHATGPT_RESPONSES_URL
        self._turn_state: str | None = None
        self._conversation_items: list[dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def reset(self) -> None:
        self._turn_state = None
        self._conversation_items.clear()

    def restore_conversation(self, items: list[dict[str, Any]]) -> None:
        if not self._enabled:
            return
        self._conversation_items = [_clone_item(item) for item in items]

    def start_turn(self, input_items: list[dict[str, Any]]) -> None:
        if not self._enabled:
            return
        del input_items
        self._turn_state = None

    def finish_turn(self) -> None:
        if not self._enabled:
            return
        self._turn_state = None

    def record_exchange(
        self,
        input_items: list[dict[str, Any]],
        response: CompletedResponse,
    ) -> None:
        if not self._enabled:
            return
        self._conversation_items.extend(_clone_item(item) for item in input_items)
        self._conversation_items.extend(
            _sanitize_output_item(item) for item in output_items(response.provider_data)
        )

    def serialize_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self._enabled:
            return tools
        return _serialize_chatgpt_tools(tools)

    def capture_response_headers(self, response: Any) -> None:
        if not self._enabled:
            return
        headers = getattr(response, "headers", None)
        if headers is None:
            return
        turn_state = headers.get(CHATGPT_TURN_STATE_HEADER)
        if isinstance(turn_state, str) and turn_state:
            self._turn_state = turn_state

    def apply_headers(self, headers: dict[str, str], *, session_id: str | None) -> None:
        if not self._enabled:
            return
        headers["Accept"] = "text/event-stream"
        headers["originator"] = "opencode"
        headers["User-Agent"] = chatgpt_user_agent()
        if session_id:
            headers["session_id"] = session_id
        if self._turn_state:
            headers[CHATGPT_TURN_STATE_HEADER] = self._turn_state

    def request_options(self) -> ResponsesRequestOptions:
        if not self._enabled:
            return ResponsesRequestOptions()
        return ResponsesRequestOptions(
            include_max_output_tokens=False,
            store=False,
            include_prompt_cache_retention=False,
            include_context_management=False,
            stream=True,
            tool_choice="auto",
            include=[],
            use_session_prompt_cache_key=True,
        )

    def build_input_payload(
        self,
        *,
        input_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self._enabled:
            return list(input_items)
        return [
            *(_clone_item(item) for item in self._conversation_items),
            *list(input_items),
        ]

    def tool_result_items_for_response(
        self,
        response: CompletedResponse,
        results: list[ToolResult],
    ) -> list[dict[str, Any]]:
        del response
        return to_function_call_output_items(results)


def output_items(provider_data: Any) -> list[dict[str, Any]]:
    if not isinstance(provider_data, dict):
        return []
    raw_items = provider_data.get("output_items")
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]


def _clone_item(item: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(item))


def _sanitize_output_item(item: dict[str, Any]) -> dict[str, Any]:
    cloned = _clone_item(item)
    return _strip_backend_ids(cloned)


def _strip_backend_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_backend_ids(item) for key, item in value.items() if key != "id"
        }
    if isinstance(value, list):
        return [_strip_backend_ids(item) for item in value]
    return value


def _serialize_chatgpt_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") == "function":
            parameters = tool.get("parameters")
            serialized.append(
                {
                    **tool,
                    "parameters": (
                        _to_chatgpt_strict_schema(parameters)
                        if isinstance(parameters, dict)
                        else parameters
                    ),
                    "strict": True,
                }
            )
            continue
        serialized.append(dict(tool))
    return serialized


def _to_chatgpt_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    transformed: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            transformed[key] = {
                prop_name: (
                    _to_chatgpt_strict_schema(prop_schema)
                    if isinstance(prop_schema, dict)
                    else prop_schema
                )
                for prop_name, prop_schema in value.items()
            }
            continue
        if key in {"items", "additionalProperties"} and isinstance(value, dict):
            transformed[key] = _to_chatgpt_strict_schema(value)
            continue
        if key in {"anyOf", "allOf", "oneOf"} and isinstance(value, list):
            transformed[key] = [
                _to_chatgpt_strict_schema(item) if isinstance(item, dict) else item
                for item in value
            ]
            continue
        transformed[key] = value

    properties = transformed.get("properties")
    if not isinstance(properties, dict):
        return transformed

    original_required = transformed.get("required")
    required = (
        [str(item) for item in original_required if isinstance(item, str)]
        if isinstance(original_required, list)
        else []
    )

    for prop_name, prop_schema in list(properties.items()):
        if prop_name in required or not isinstance(prop_schema, dict):
            continue
        properties[prop_name] = {
            "anyOf": [
                prop_schema,
                {"type": "null"},
            ]
        }

    transformed["required"] = list(properties.keys())
    return transformed
