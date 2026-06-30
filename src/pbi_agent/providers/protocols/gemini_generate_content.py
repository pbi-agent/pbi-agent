"""Gemini ``generateContent`` protocol adapter.

This adapter owns the Vertex/Gemini REST ``generateContent`` request/response
shape while the provider wrapper owns auth, endpoint selection, and transport.
"""

from __future__ import annotations

import json
from typing import Any

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.config import Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
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
from pbi_agent.web.uploads import load_uploaded_image


class GeminiGenerateContentProtocol(ResponseProtocol):
    """State and wire shape for Gemini REST ``generateContent``."""

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
        self.system_prompt = system_prompt or get_system_prompt(
            settings=self.settings,
            excluded_tools=self.excluded_tools,
        )
        self.contents: list[dict[str, Any]] = []
        self.tools: list[dict[str, Any]] = []
        self.refresh_tools()

    def reset_conversation(self) -> None:
        self.contents.clear()

    def set_system_prompt(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt

    def set_excluded_tools(self, excluded_tools: set[str]) -> None:
        self.excluded_tools = default_excluded_tool_names(excluded_tools)
        self.refresh_tools()

    def refresh_tools(self) -> None:
        excluded_tools = effective_excluded_tool_names(
            self.settings, self.excluded_tools
        )
        declarations: list[dict[str, Any]] = []
        for spec in self.tool_catalog.get_specs(excluded_names=excluded_tools):
            if spec.is_freeform:
                continue
            declaration: dict[str, Any] = {
                "name": spec.name,
                "description": spec.description,
            }
            if spec.parameters_schema:
                declaration["parameters"] = _normalize_gemini_schema(
                    spec.parameters_schema
                )
            declarations.append(declaration)
        self.tools = [{"functionDeclarations": declarations}] if declarations else []

    def set_runtime_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.refresh_tools()

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        self.contents = [
            content
            for message in messages
            if (content := _message_record_to_content(message)) is not None
        ]

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        contents: list[dict[str, Any]] = []
        for item in items:
            contents.extend(_history_item_to_contents(item))
        self.contents = contents

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
            content = _user_input_to_content(user_input)
            self.contents.append(content)
            return user_input.text or "image input"

        if tool_result_items is not None:
            self.contents.extend(
                dict(item) for item in tool_result_items if isinstance(item, dict)
            )
            if steer_user_input is not None:
                self.contents.append(_user_input_to_content(steer_user_input))
            return [{"type": "function_result"}]

        raise ValueError("Either user_input or tool_result_items is required")

    def build_request_body(self, *, instructions: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "contents": [dict(content) for content in self.contents],
            "generationConfig": {"maxOutputTokens": self.settings.max_tokens},
        }
        if instructions:
            body["systemInstruction"] = {"parts": [{"text": instructions}]}
        if self.tools:
            body["tools"] = self.tools
        return body

    def parse_response(self, response_json: dict[str, object]) -> CompletedResponse:
        candidates = response_json.get("candidates")
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        function_calls: list[ToolCall] = []
        model_contents: list[dict[str, Any]] = []
        thought_signatures: list[str] = []

        if isinstance(candidates, list):
            for candidate_index, candidate in enumerate(candidates):
                if not isinstance(candidate, dict):
                    continue
                content = candidate.get("content")
                if not isinstance(content, dict):
                    continue
                normalized_content = _normalize_model_content(content)
                if normalized_content is not None:
                    model_contents.append(normalized_content)
                for part_index, part in enumerate(_content_parts(content)):
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        if part.get("thought") is True:
                            reasoning_parts.append(text)
                        else:
                            text_parts.append(text)
                    signature = part.get("thoughtSignature")
                    if isinstance(signature, str) and signature:
                        thought_signatures.append(signature)
                    function_call = part.get("functionCall")
                    if isinstance(function_call, dict):
                        function_calls.append(
                            _parse_function_call(
                                function_call,
                                candidate_index=candidate_index,
                                part_index=part_index,
                            )
                        )

        usage_obj = response_json.get("usageMetadata")
        usage = _parse_usage(usage_obj, model=_response_model_name(response_json))
        response_id = response_json.get("responseId") or response_json.get("id")

        return CompletedResponse(
            response_id=response_id if isinstance(response_id, str) else None,
            text="\n\n".join(part for part in text_parts if part.strip()).strip(),
            usage=usage,
            function_calls=function_calls,
            reasoning_content="\n\n".join(
                part for part in reasoning_parts if part.strip()
            ).strip(),
            provider_data={
                "model_contents": model_contents,
                "thought_signatures": thought_signatures,
            },
        )

    def record_response(self, response: CompletedResponse) -> None:
        provider_data = response.provider_data
        if not isinstance(provider_data, dict):
            return
        model_contents = provider_data.get("model_contents")
        if not isinstance(model_contents, list):
            return
        self.contents.extend(
            dict(content) for content in model_contents if isinstance(content, dict)
        )

    def render_response(
        self,
        display: DisplayProtocol,
        response: CompletedResponse,
    ) -> None:
        if response.reasoning_summary or response.reasoning_content:
            display.render_thinking(
                _reasoning_body_text(
                    response.reasoning_content,
                    response.reasoning_summary,
                ),
                title=response.reasoning_summary or None,
            )
        if response.text:
            display.render_markdown(response.text)

    def serialize_tool_result(
        self,
        result: ToolResult,
        call: ToolCall | None = None,
    ) -> dict[str, Any]:
        name = call.name if call is not None else ""
        response_payload = _tool_result_response_payload(result)
        return {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": name,
                        "response": response_payload,
                    }
                }
            ],
        }


def _message_record_to_content(message: MessageRecord) -> dict[str, Any] | None:
    if message.role not in {"user", "assistant"}:
        return None
    if not message.content and not message.image_attachments:
        return None
    if message.role == "user":
        images = [
            load_uploaded_image(attachment.upload_id)
            for attachment in message.image_attachments
        ]
        return _user_input_to_content(
            UserTurnInput(text=message.content, images=images)
        )
    return _model_text_content(message.content)


def _history_item_to_contents(item: dict[str, Any]) -> list[dict[str, Any]]:
    item_type = item.get("type")
    if item_type == "message":
        message = item.get("message")
        if isinstance(message, MessageRecord):
            content = _message_record_to_content(message)
            return [content] if content is not None else []
        return []
    if item_type == "tool_call":
        content = _tool_call_history_content(item)
        return [content] if content is not None else []
    if item_type == "tool_call_group":
        parts: list[dict[str, Any]] = []
        for call_item in item.get("calls", []):
            if isinstance(call_item, dict):
                parts.extend(_tool_call_history_parts(call_item))
        return [{"role": "model", "parts": parts}] if parts else []
    if item_type == "tool_result":
        content = _tool_result_history_content(item)
        return [content] if content is not None else []
    if item_type == "tool_result_group":
        result_parts: list[dict[str, Any]] = []
        for result_item in item.get("results", []):
            if isinstance(result_item, dict):
                result_parts.extend(_tool_result_history_parts(result_item))
        return [{"role": "user", "parts": result_parts}] if result_parts else []
    return []


def _user_input_to_content(user_input: UserTurnInput) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    if user_input.text:
        parts.append({"text": user_input.text})
    parts.extend(_image_part(image) for image in user_input.images)
    if not parts:
        parts.append({"text": ""})
    return {"role": "user", "parts": parts}


def _model_text_content(text: str) -> dict[str, Any]:
    return {"role": "model", "parts": [{"text": text}] if text else []}


def _image_part(image: ImageAttachment) -> dict[str, Any]:
    return {
        "inlineData": {
            "mimeType": image.mime_type,
            "data": image.data_base64,
        }
    }


def _tool_call_history_content(item: dict[str, Any]) -> dict[str, Any] | None:
    parts = _tool_call_history_parts(item)
    return {"role": "model", "parts": parts} if parts else None


def _tool_call_history_parts(item: dict[str, Any]) -> list[dict[str, Any]]:
    name = str(item.get("name") or "")
    if not name:
        return []
    arguments = item.get("arguments") or {}
    return [{"functionCall": {"name": name, "args": arguments}}]


def _tool_result_history_content(item: dict[str, Any]) -> dict[str, Any] | None:
    parts = _tool_result_history_parts(item)
    return {"role": "user", "parts": parts} if parts else None


def _tool_result_history_parts(item: dict[str, Any]) -> list[dict[str, Any]]:
    name = str(item.get("name") or "")
    if not name:
        return []
    output = item.get("output")
    payload: dict[str, Any] = {"output": output if output is not None else ""}
    call_id = str(item.get("call_id") or "")
    if call_id:
        payload["call_id"] = call_id
    if item.get("is_error"):
        payload["is_error"] = True
    return [{"functionResponse": {"name": name, "response": payload}}]


def _content_parts(content: dict[str, Any]) -> list[dict[str, Any]]:
    parts = content.get("parts")
    if isinstance(parts, dict):
        return [parts]
    if not isinstance(parts, list):
        return []
    return [part for part in parts if isinstance(part, dict)]


def _normalize_model_content(content: dict[str, Any]) -> dict[str, Any] | None:
    parts = _content_parts(content)
    if not parts:
        return None
    return {"role": "model", "parts": [dict(part) for part in parts]}


def _parse_function_call(
    function_call: dict[str, Any],
    *,
    candidate_index: int,
    part_index: int,
) -> ToolCall:
    name = str(function_call.get("name") or "")
    call_id = function_call.get("id")
    if not isinstance(call_id, str) or not call_id:
        call_id = f"gemini_call_{candidate_index}_{part_index}"
    arguments = function_call.get("args")
    if arguments is None:
        arguments = function_call.get("arguments")
    return ToolCall(call_id=call_id, name=name, arguments=arguments)


def _parse_usage(usage_obj: object, *, model: str) -> TokenUsage:
    usage = usage_obj if isinstance(usage_obj, dict) else {}
    prompt_tokens = _usage_value(usage, "promptTokenCount")
    candidate_tokens = _usage_value(usage, "candidatesTokenCount")
    total_tokens = _usage_value(usage, "totalTokenCount")
    reasoning_tokens = _usage_value(usage, "thoughtsTokenCount")
    cached_tokens = _usage_value(usage, "cachedContentTokenCount")
    return TokenUsage(
        input_tokens=prompt_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=candidate_tokens,
        reasoning_tokens=reasoning_tokens,
        provider_total_tokens=total_tokens,
        context_tokens=total_tokens,
        model=model,
    )


def _usage_value(usage: dict[Any, Any], key: str) -> int:
    value = usage.get(key, 0)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _response_model_name(response_json: dict[str, object]) -> str:
    for key in ("modelVersion", "model"):
        value = response_json.get(key)
        if isinstance(value, str):
            return value
    return ""


def _tool_result_response_payload(result: ToolResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "call_id": result.call_id,
        "output": _decode_tool_output(result.output_json),
    }
    if result.is_error:
        payload["is_error"] = True
    if result.attachments:
        payload["attachments"] = [
            {
                "mime_type": attachment.mime_type,
                "data": attachment.data_base64,
            }
            for attachment in result.attachments
        ]
    return payload


def _decode_tool_output(output_json: str) -> Any:
    try:
        return json.loads(output_json)
    except json.JSONDecodeError:
        return output_json


def _normalize_gemini_schema(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if key == "required" and isinstance(child, list) and not child:
                continue
            normalized[key] = _normalize_gemini_schema(child)
        return normalized
    if isinstance(value, list):
        return [_normalize_gemini_schema(item) for item in value]
    return value


def _reasoning_body_text(
    reasoning_content: str | None,
    reasoning_summary: str | None,
) -> str | None:
    parts = [part for part in (reasoning_content, reasoning_summary) if part]
    if not parts:
        return None
    return "\n\n".join(parts)
