"""OpenAI-compatible Chat Completions protocol adapter."""

from __future__ import annotations

import json
from typing import Any

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.config import Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.media import data_url_for_image
from pbi_agent.models.messages import (
    CompletedResponse,
    TokenUsage,
    ToolCall,
    UserTurnInput,
)
from pbi_agent.providers.protocols.base import ResponseProtocol
from pbi_agent.session_store import MessageRecord
from pbi_agent.tools.availability import (
    default_excluded_tool_names,
    effective_excluded_tool_names,
)
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.types import ToolResult


class ChatCompletionsProtocol(ResponseProtocol):
    """State and wire shape for OpenAI-compatible Chat Completions."""

    def __init__(
        self,
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> None:
        self.settings = settings
        self.tool_catalog = tool_catalog or ToolCatalog.from_builtin_registry()
        self.excluded_tools = default_excluded_tool_names(excluded_tools)
        self.tools: list[dict[str, Any]] = []
        self.refresh_tools()
        self.system_prompt = system_prompt or get_system_prompt(
            settings=self.settings,
            excluded_tools=self.excluded_tools,
        )
        self.messages: list[dict[str, Any]] = []

    def reset_conversation(self) -> None:
        self.messages.clear()

    def set_system_prompt(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt

    def refresh_tools(self) -> None:
        excluded_tools = effective_excluded_tool_names(
            self.settings, self.excluded_tools
        )
        self.tools = self.tool_catalog.get_openai_chat_tool_definitions(
            excluded_names=excluded_tools
        )

    def set_runtime_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.refresh_tools()

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        self.messages = [
            {"role": message.role, "content": message.content}
            for message in messages
            if message.role in {"user", "assistant"} and message.content
        ]

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        self.messages = _history_items_to_messages(items)

    def accept_turn(
        self,
        *,
        user_message: str | None,
        user_input: UserTurnInput | None,
        tool_result_items: list[dict[str, Any]] | None,
    ) -> str | list[dict[str, Any]]:
        if user_input is None and user_message is not None:
            user_input = UserTurnInput(text=user_message)

        if user_input is not None:
            if user_input.images:
                raise ValueError(
                    "Generic provider image inputs are not enabled in this build."
                )
            self.messages.append({"role": "user", "content": user_input.text})
            return user_input.text

        if tool_result_items is not None:
            self.messages.extend(tool_result_items)
            return tool_result_items

        raise ValueError("Either user_input or tool_result_items is required")

    def build_request_body(self, *, instructions: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": instructions}]
        messages.extend(self.messages)

        body: dict[str, Any] = {
            "messages": messages,
            "tools": self.tools,
            "tool_choice": "auto",
            "max_tokens": self.settings.max_tokens,
        }
        if self.settings.model:
            body["model"] = self.settings.model
        return body

    def parse_response(self, response_json: dict[str, object]) -> CompletedResponse:
        choices = response_json.get("choices", [])
        messages = _extract_choice_messages(choices)
        text = "".join(
            _extract_message_text(message.get("content")) for message in messages
        )
        function_calls = [
            function_call
            for message in messages
            for function_call in _parse_tool_calls(message.get("tool_calls"))
        ]

        assistant_message = _normalize_assistant_messages(messages)

        usage_obj = response_json.get("usage", {})
        if not isinstance(usage_obj, dict):
            usage_obj = {}
        prompt_tokens = int(usage_obj.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage_obj.get("completion_tokens", 0) or 0)
        total_tokens = int(usage_obj.get("total_tokens", 0) or 0)
        completion_details = usage_obj.get("completion_tokens_details", {})
        reasoning_tokens = (
            int(completion_details.get("reasoning_tokens", 0) or 0)
            if isinstance(completion_details, dict)
            else 0
        )

        response_id = response_json.get("id")
        return CompletedResponse(
            response_id=response_id if isinstance(response_id, str) else None,
            text=text,
            usage=TokenUsage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
                context_tokens=total_tokens or (prompt_tokens + completion_tokens),
                model=_response_model_name(response_json),
            ),
            function_calls=function_calls,
            provider_data={"assistant_message": assistant_message},
        )

    def record_response(self, response: CompletedResponse) -> None:
        assistant_message = response.provider_data.get("assistant_message")
        if isinstance(assistant_message, dict):
            self.messages.append(assistant_message)

    def render_response(
        self,
        display: DisplayProtocol,
        response: CompletedResponse,
    ) -> None:
        if response.text:
            display.render_markdown(response.text)

    def serialize_tool_result(self, result: ToolResult) -> dict[str, object]:
        content: str | list[dict[str, Any]] = result.output_json
        if result.attachments:
            content = [{"type": "text", "text": result.output_json}]
            for attachment in result.attachments:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url_for_image(attachment)},
                    }
                )
        return {
            "role": "tool",
            "tool_call_id": result.call_id,
            "content": content,
        }


def _response_model_name(response_json: dict[str, object]) -> str:
    model = response_json.get("model")
    return model if isinstance(model, str) else ""


def _history_items_to_messages(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") == "tool_result_group":
            for result in item.get("results", []):
                if (
                    isinstance(result, dict)
                    and (restored := _history_item_to_message(result)) is not None
                ):
                    messages.append(restored)
            continue
        if (restored := _history_item_to_message(item)) is not None:
            messages.append(restored)
    return messages


def _history_item_to_message(item: dict[str, Any]) -> dict[str, Any] | None:
    item_type = item.get("type")
    if item_type == "message":
        message = item.get("message")
        if (
            isinstance(message, MessageRecord)
            and message.role in {"user", "assistant"}
            and message.content
        ):
            return {"role": message.role, "content": message.content}
        return None
    if item_type == "tool_call":
        call_id = str(item.get("call_id") or "")
        name = str(item.get("name") or "")
        if not call_id or not name:
            return None
        arguments = item.get("arguments")
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": (
                            arguments
                            if isinstance(arguments, str)
                            else json.dumps(arguments or {})
                        ),
                    },
                }
            ],
        }
    if item_type == "tool_call_group":
        tool_calls: list[dict[str, Any]] = []
        for call in item.get("calls", []):
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("call_id") or "")
            name = str(call.get("name") or "")
            if not call_id or not name:
                continue
            arguments = call.get("arguments")
            tool_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": (
                            arguments
                            if isinstance(arguments, str)
                            else json.dumps(arguments or {})
                        ),
                    },
                }
            )
        if not tool_calls:
            return None
        return {"role": "assistant", "content": "", "tool_calls": tool_calls}
    if item_type == "tool_result":
        call_id = str(item.get("call_id") or "")
        if not call_id:
            return None
        output = item.get("output")
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": output if isinstance(output, str) else json.dumps(output),
        }
    return None


def _extract_choice_messages(choices: object) -> list[dict[str, Any]]:
    if not isinstance(choices, list):
        return []

    messages: list[dict[str, Any]] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message", {})
        if isinstance(message, dict):
            messages.append(message)
    return messages


def _extract_message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type", "")).strip().lower()
        text_value = part.get("text")
        if isinstance(text_value, str) and part_type in {"text", "output_text"}:
            text_parts.append(text_value)
    return "".join(text_parts).strip()


def _parse_tool_calls(raw_tool_calls: object) -> list[ToolCall]:
    if not isinstance(raw_tool_calls, list):
        return []

    function_calls: list[ToolCall] = []
    for call in raw_tool_calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function", {})
        if not isinstance(function, dict):
            function = {}
        raw_args = function.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                arguments: dict[str, Any] | str | None = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = raw_args
        else:
            arguments = raw_args
        function_calls.append(
            ToolCall(
                call_id=str(call.get("id", "")),
                name=str(function.get("name", "")),
                arguments=arguments,
            )
        )
    return function_calls


def _normalize_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {"role": "assistant"}

    content = message.get("content")
    normalized_content = _normalize_message_content(content)
    if normalized_content is not None:
        normalized["content"] = normalized_content

    normalized_tool_calls = _normalize_tool_calls(message.get("tool_calls"))
    if normalized_tool_calls:
        normalized["tool_calls"] = normalized_tool_calls

    if "content" not in normalized and "tool_calls" not in normalized:
        normalized["content"] = ""

    return normalized


def _normalize_assistant_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    if not messages:
        return _normalize_assistant_message({})
    if len(messages) == 1:
        return _normalize_assistant_message(messages[0])

    normalized: dict[str, Any] = {"role": "assistant"}
    content_parts: list[Any] = []
    tool_calls: list[dict[str, Any]] = []
    for message in messages:
        normalized_message = _normalize_assistant_message(message)
        content = normalized_message.get("content")
        if isinstance(content, str):
            if content:
                content_parts.append(content)
        elif isinstance(content, list):
            content_parts.extend(content)
        raw_tool_calls = normalized_message.get("tool_calls")
        if isinstance(raw_tool_calls, list):
            tool_calls.extend(call for call in raw_tool_calls if isinstance(call, dict))

    if content_parts:
        if all(isinstance(part, str) for part in content_parts):
            normalized["content"] = "".join(content_parts)
        else:
            normalized["content"] = content_parts
    if tool_calls:
        normalized["tool_calls"] = tool_calls
    if "content" not in normalized and "tool_calls" not in normalized:
        normalized["content"] = ""
    return normalized


def _normalize_message_content(content: object) -> str | list[dict[str, str]] | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None

    normalized_parts: list[dict[str, str]] = []
    for part in content:
        if not isinstance(part, dict):
            continue

        part_type = str(part.get("type", "")).strip().lower()
        if part_type in {"text", "output_text"}:
            text_value = part.get("text")
            if isinstance(text_value, str):
                normalized_parts.append({"type": "text", "text": text_value})
                continue

        if part_type == "refusal":
            refusal = part.get("refusal")
            if isinstance(refusal, str):
                normalized_parts.append({"type": "refusal", "refusal": refusal})

    return normalized_parts or None


def _normalize_tool_calls(raw_tool_calls: object) -> list[dict[str, Any]]:
    if not isinstance(raw_tool_calls, list):
        return []

    normalized_calls: list[dict[str, Any]] = []
    for call in raw_tool_calls:
        if not isinstance(call, dict):
            continue

        function = call.get("function", {})
        if not isinstance(function, dict):
            function = {}

        name = str(function.get("name", "")).strip()
        if not name:
            continue

        raw_arguments = function.get("arguments", "{}")
        if isinstance(raw_arguments, str):
            arguments = raw_arguments or "{}"
        else:
            arguments = json.dumps(raw_arguments)

        normalized_calls.append(
            {
                "id": str(call.get("id", "")),
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": arguments,
                },
            }
        )

    return normalized_calls
