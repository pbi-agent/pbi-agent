from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from typing import Any

from pbi_agent import __version__
from pbi_agent.auth.providers.openai_chatgpt import OPENAI_CHATGPT_RESPONSES_URL
from pbi_agent.agent.tool_runtime import to_function_call_output_items
from pbi_agent.models.messages import CompletedResponse, ToolCall
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
        self._turn_replay_items: list[dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def reset(self) -> None:
        self._turn_state = None
        self._turn_replay_items.clear()

    def start_turn(self, input_items: list[dict[str, Any]]) -> None:
        if not self._enabled:
            return
        self._turn_state = None
        self._turn_replay_items = [dict(item) for item in input_items]

    def record_tool_result_request(self, input_items: list[dict[str, Any]]) -> None:
        if not self._enabled:
            return
        self._turn_replay_items.extend(dict(item) for item in input_items)

    def finish_turn(self) -> None:
        if not self._enabled:
            return
        self._turn_state = None
        self._turn_replay_items.clear()

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
        include_previous_response_id: bool,
    ) -> list[dict[str, Any]]:
        if (
            not self._enabled
            or include_previous_response_id
            or not has_function_call_output_items(input_items)
            or not self._turn_replay_items
        ):
            return list(input_items)
        return [
            *(dict(item) for item in self._turn_replay_items),
            *list(input_items),
        ]

    def should_retry_without_previous_response_id(
        self,
        *,
        input_items: list[dict[str, Any]],
        include_previous_response_id: bool,
        previous_response_id: str | None,
        error_payload: dict[str, Any] | None,
    ) -> bool:
        return (
            self._enabled
            and include_previous_response_id
            and previous_response_id is not None
            and has_function_call_output_items(input_items)
            and is_invalid_request_error(error_payload)
        )

    def tool_result_items_for_response(
        self,
        response: CompletedResponse,
        results: list[ToolResult],
    ) -> list[dict[str, Any]]:
        output_items = to_function_call_output_items(results)
        if not self._enabled:
            return output_items

        calls_by_id = {call.call_id: call for call in response.function_calls}
        raw_items_by_id = function_call_items_by_call_id(response.provider_data)
        items: list[dict[str, Any]] = []
        for output_item in output_items:
            call_id = output_item.get("call_id")
            if not isinstance(call_id, str):
                items.append(output_item)
                continue
            raw_item = raw_items_by_id.get(call_id)
            if raw_item is not None:
                items.append(dict(raw_item))
            else:
                call = calls_by_id.get(call_id)
                if call is not None:
                    items.append(function_call_input_item(call))
            items.append(output_item)
        return items


def function_call_input_item(call: ToolCall) -> dict[str, Any]:
    arguments = call.arguments
    if isinstance(arguments, str):
        encoded_arguments = arguments
    elif arguments is None:
        encoded_arguments = "{}"
    else:
        encoded_arguments = json.dumps(arguments)
    return {
        "type": "function_call",
        "call_id": call.call_id,
        "name": call.name,
        "arguments": encoded_arguments,
    }


def function_call_items_by_call_id(provider_data: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(provider_data, dict):
        return {}
    raw_items = provider_data.get("function_call_items")
    if not isinstance(raw_items, dict):
        return {}
    items: dict[str, dict[str, Any]] = {}
    for call_id, item in raw_items.items():
        if isinstance(call_id, str) and isinstance(item, dict):
            items[call_id] = item
    return items


def has_function_call_output_items(input_items: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(item, dict) and item.get("type") == "function_call_output"
        for item in input_items
    )


def is_invalid_request_error(error_payload: dict[str, Any] | None) -> bool:
    if not isinstance(error_payload, dict):
        return False
    if error_payload.get("type") == "invalid_request_error":
        return True
    error = error_payload.get("error")
    return isinstance(error, dict) and error.get("type") == "invalid_request_error"


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
