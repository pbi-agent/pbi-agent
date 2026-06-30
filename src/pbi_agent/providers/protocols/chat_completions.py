"""OpenAI-compatible Chat Completions protocol adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
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


_THINK_TAG_RE = re.compile(
    r"<think(?:\s+[^>]*)?>(.*?)</think\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class _ExtractedText:
    text: str
    reasoning: str = ""


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
        steer_user_input: UserTurnInput | None = None,
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
            if steer_user_input is not None:
                if steer_user_input.images:
                    raise ValueError(
                        "Generic provider image inputs are not enabled in this build."
                    )
                self.messages.append({"role": "user", "content": steer_user_input.text})
            return tool_result_items

        raise ValueError("Either user_input or tool_result_items is required")

    def build_request_body(self, *, instructions: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": instructions}]
        messages.extend(self.messages)

        body: dict[str, Any] = {
            "messages": messages,
            "max_tokens": self.settings.max_tokens,
        }
        if self.tools:
            body["tools"] = self.tools
            body["tool_choice"] = "auto"
        if self.settings.model:
            body["model"] = self.settings.model
        return body

    def parse_response(self, response_json: dict[str, object]) -> CompletedResponse:
        choices = response_json.get("choices", [])
        messages = _extract_choice_messages(choices)
        extracted_text = [
            _extract_message_text(message.get("content")) for message in messages
        ]
        text = "".join(item.text for item in extracted_text)
        reasoning_parts: list[str] = []
        for message, item in zip(messages, extracted_text, strict=False):
            _append_unique_text(reasoning_parts, _extract_message_reasoning(message))
            _append_unique_text(reasoning_parts, item.reasoning)
        reasoning_content = "\n\n".join(reasoning_parts).strip()
        function_calls = [
            function_call
            for message in messages
            for function_call in _parse_tool_calls(message.get("tool_calls"))
        ]

        assistant_message = _normalize_assistant_messages(messages)

        response_id = response_json.get("id")
        return CompletedResponse(
            response_id=response_id if isinstance(response_id, str) else None,
            text=text,
            usage=_parse_usage(response_json),
            function_calls=function_calls,
            reasoning_content=reasoning_content,
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
        if response.reasoning_summary or response.reasoning_content:
            display.render_thinking(
                response.reasoning_content or response.reasoning_summary,
                title=response.reasoning_summary or None,
            )
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


def _parse_usage(response_json: dict[str, object]) -> TokenUsage:
    usage = _usage_dict(response_json.get("usage"))
    prompt_details = _usage_dict(usage.get("prompt_tokens_details"))
    input_details = _usage_dict(usage.get("input_tokens_details"))
    completion_details = _usage_dict(usage.get("completion_tokens_details"))

    input_tokens = _usage_value(usage, "prompt_tokens")
    output_tokens = _usage_value(usage, "completion_tokens")
    total_tokens = _usage_value(usage, "total_tokens")

    return TokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=_first_usage_detail_value(
            detail_sources=(prompt_details, input_details, usage),
            keys=(
                "cached_tokens",
                "cached_input_tokens",
                "cache_read_input_tokens",
            ),
        ),
        cache_write_tokens=_first_usage_detail_value(
            detail_sources=(prompt_details, input_details, usage),
            keys=("cache_write_tokens", "cache_creation_input_tokens"),
        ),
        cache_write_1h_tokens=_first_usage_detail_value(
            detail_sources=(prompt_details, input_details, usage),
            keys=("cache_write_1h_tokens", "cache_creation_input_tokens_1h"),
        ),
        output_tokens=output_tokens,
        reasoning_tokens=_usage_value(completion_details, "reasoning_tokens"),
        context_tokens=total_tokens or (input_tokens + output_tokens),
        model=_response_model_name(response_json),
    )


def _usage_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _usage_value(usage_obj: object, key: str) -> int:
    if not isinstance(usage_obj, dict):
        return 0
    return _coerce_usage_int(usage_obj.get(key))


def _first_usage_detail_value(
    *,
    detail_sources: tuple[dict[str, object], ...],
    keys: tuple[str, ...],
) -> int:
    for detail_source in detail_sources:
        for key in keys:
            value = _usage_value(detail_source, key)
            if value:
                return value
    return 0


def _coerce_usage_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return int(float(value))
            except ValueError:
                return 0
    return 0


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


def _extract_message_text(content: object) -> _ExtractedText:
    if isinstance(content, str):
        return _split_tagged_reasoning(content)
    if not isinstance(content, list):
        return _ExtractedText("")

    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type", "")).strip().lower()
        text_value = part.get("text")
        if isinstance(text_value, str) and part_type in {"text", "output_text"}:
            extracted = _split_tagged_reasoning(text_value)
            if extracted.text:
                text_parts.append(extracted.text)
            _append_unique_text(reasoning_parts, extracted.reasoning)
    return _ExtractedText(
        "".join(text_parts).strip(),
        "\n\n".join(reasoning_parts).strip(),
    )


def _split_tagged_reasoning(text: str) -> _ExtractedText:
    matches = list(_THINK_TAG_RE.finditer(text))
    if not matches:
        return _ExtractedText(text)

    reasoning_parts: list[str] = []

    def replace_tag(match: re.Match[str]) -> str:
        _append_unique_text(reasoning_parts, match.group(1))
        return ""

    visible_text = _THINK_TAG_RE.sub(replace_tag, text)
    if not text[: matches[0].start()].strip():
        visible_text = visible_text.lstrip()
    if not text[matches[-1].end() :].strip():
        visible_text = visible_text.rstrip()
    return _ExtractedText(
        visible_text,
        "\n\n".join(reasoning_parts).strip(),
    )


def _append_unique_text(parts: list[str], text: str) -> None:
    normalized = text.strip()
    if normalized and normalized not in parts:
        parts.append(normalized)


def _extract_message_reasoning(message: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("reasoning", "reasoning_content", "reasoning_details"):
        text = _extract_reasoning_text(message.get(key))
        if text and text not in parts:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _extract_reasoning_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n\n".join(
            text for item in value if (text := _extract_reasoning_text(item))
        ).strip()
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("text", "content", "summary"):
            text = _extract_reasoning_text(value.get(key))
            if text and text not in parts:
                parts.append(text)
        return "\n\n".join(parts).strip()
    return ""


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
    normalized_content = _normalize_replay_message_content(content)
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


def _normalize_replay_message_content(
    content: object,
) -> str | list[dict[str, str]] | None:
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
                if text_value:
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
