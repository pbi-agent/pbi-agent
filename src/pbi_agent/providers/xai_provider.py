"""xAI Responses HTTP provider.

Uses direct synchronous HTTP calls to xAI's Responses API. Conversation
history is managed server-side via ``previous_response_id``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from pbi_agent import __version__
from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import (
    execute_tool_calls as _execute_tool_calls,
    to_function_call_output_items,
)
from pbi_agent.config import Settings
from pbi_agent.models.messages import CompletedResponse, TokenUsage, ToolCall
from pbi_agent.providers.base import Provider
from pbi_agent.tools.registry import get_openai_tool_definitions
from pbi_agent.ui.display_protocol import DisplayProtocol

_REQUEST_TIMEOUT_SECS = 3600.0
_REASONING_EFFORT_MODELS = ("grok-3-mini",)
_ENCRYPTED_REASONING_MODELS = ("grok-4",)
_EFFORT_MAP: dict[str, str] = {
    "low": "low",
    "medium": "high",
    "high": "high",
    "xhigh": "high",
}
_HTTP_ERROR_TYPES: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    405: "invalid_request_error",
    415: "invalid_request_error",
    422: "invalid_request_error",
    429: "rate_limit_error",
}
_HTTP_ERROR_MESSAGES: dict[int, str] = {
    400: "Request body or URL contains invalid input.",
    401: "No authorization header or an invalid authorization token was provided.",
    403: "API key or team lacks permission to perform this action.",
    404: "The requested model or endpoint could not be found.",
    405: "HTTP method is not allowed for this endpoint.",
    415: "Request body is missing or Content-Type is not application/json.",
    422: "Request body contains an invalid field format.",
    429: "Too many requests. Reduce request rate or increase your rate limit.",
}


class XAIProvider(Provider):
    """Provider backed by xAI's synchronous Responses HTTP API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tools = get_openai_tool_definitions()
        self._instructions = get_system_prompt()
        self._previous_response_id: str | None = None

    def connect(self) -> None:
        if not self._settings.api_key:
            raise ValueError(
                "Missing API key. Set PBI_AGENT_API_KEY in environment or pass "
                "--api-key."
            )

    def close(self) -> None:
        pass

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        tool_result_items: list[dict[str, Any]] | None = None,
        instructions: str | None = None,
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> CompletedResponse:
        if user_message is not None:
            input_items: list[dict[str, Any]] = [_build_user_input_item(user_message)]
        elif tool_result_items is not None:
            input_items = tool_result_items
        else:
            raise ValueError("Either user_message or tool_result_items is required")

        result = self._http_request(
            input_items=input_items,
            instructions=instructions or self._instructions,
            display=display,
        )
        self._previous_response_id = result.response_id
        session_usage.add(result.usage)
        turn_usage.add(result.usage)
        display.session_usage(session_usage)

        if result.reasoning_summary or result.reasoning_content:
            display.render_thinking(
                _reasoning_body_text(
                    result.reasoning_content,
                    result.reasoning_summary,
                ),
                title=result.reasoning_summary or None,
            )

        if result.text:
            display.render_markdown(result.text)

        return result

    def execute_tool_calls(
        self,
        response: CompletedResponse,
        *,
        max_workers: int,
        display: DisplayProtocol,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not response.function_calls:
            return [], False

        display.function_start(len(response.function_calls))
        batch = _execute_tool_calls(response.function_calls, max_workers=max_workers)

        for result in batch.results:
            call = _find_by_id(response.function_calls, result.call_id)
            display.function_result(
                name=call.name if call else "unknown",
                success=not result.is_error,
                call_id=result.call_id,
                arguments=call.arguments if call else None,
            )
        display.tool_group_end()

        return to_function_call_output_items(batch.results), batch.had_errors

    def _http_request(
        self,
        *,
        input_items: list[dict[str, Any]],
        instructions: str,
        display: DisplayProtocol,
    ) -> CompletedResponse:
        display.wait_start(_waiting_message_for_input_items(input_items))

        body = self._build_request_body(
            input_items=input_items,
            instructions=instructions,
        )
        request_data = json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._settings.api_key}",
            "User-Agent": f"pbi-agent/{__version__}",
        }

        max_retries = self._settings.max_retries
        last_error: Exception | None = None
        last_error_message: str | None = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                display.retry_notice(attempt, max_retries)

            try:
                req = urllib.request.Request(
                    self._settings.responses_url,
                    data=request_data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECS) as resp:
                    response_json = json.loads(resp.read().decode("utf-8"))

                result = self._parse_response(response_json)
                display.wait_stop()
                return result
            except urllib.error.HTTPError as exc:
                error_body = _read_error_body(exc)
                error_payload = _normalize_http_error(exc, error_body)
                if exc.code == 429:
                    if attempt >= max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            _format_error_message(
                                f"xAI rate limit exceeded after {max_retries + 1} attempts",
                                error_payload,
                            )
                        ) from exc
                    wait = _extract_retry_after(exc, attempt)
                    display.rate_limit_notice(
                        wait_seconds=wait,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    time.sleep(wait)
                    continue

                if exc.code >= 500:
                    last_error = exc
                    last_error_message = _format_error_message(
                        f"xAI request failed after {max_retries + 1} attempts",
                        error_payload,
                    )
                    continue

                display.wait_stop()
                raise RuntimeError(
                    _format_error_message(
                        f"xAI Responses API error {exc.code}",
                        error_payload,
                    )
                ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                last_error_message = None
                continue

        display.wait_stop()
        if last_error is not None:
            if last_error_message:
                raise RuntimeError(last_error_message) from last_error
            raise RuntimeError(
                f"xAI request failed after {max_retries + 1} attempts: {last_error}"
            ) from last_error
        raise RuntimeError("xAI request failed after retries.")

    def _build_request_body(
        self,
        *,
        input_items: list[dict[str, Any]],
        instructions: str | None,
    ) -> dict[str, Any]:
        request_input_items = list(input_items)
        if instructions and not self._previous_response_id:
            request_input_items.insert(0, _build_system_input_item(instructions))

        body: dict[str, Any] = {
            "model": self._settings.model,
            "max_output_tokens": self._settings.max_tokens,
            "input": request_input_items,
            "tools": self._tools,
            "parallel_tool_calls": True,
            "stream": False,
        }
        if self._previous_response_id:
            body["previous_response_id"] = self._previous_response_id

        include = _response_include(self._settings.model)
        if include:
            body["include"] = include

        reasoning = _reasoning_request(
            self._settings.model,
            self._settings.reasoning_effort,
        )
        if reasoning:
            body["reasoning"] = reasoning

        return body

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        text_parts: list[str] = []
        reasoning_summary_parts: list[str] = []
        reasoning_content_parts: list[str] = []
        encrypted_reasoning_parts: list[str] = []
        function_calls: list[ToolCall] = []

        output_items = response_json.get("output", [])
        if not isinstance(output_items, list):
            output_items = []

        for item in output_items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")

            if item_type == "reasoning":
                reasoning_summary_parts.extend(
                    _extract_reasoning_summary_texts(item.get("summary"))
                )
                encrypted_content = item.get("encrypted_content")
                if isinstance(encrypted_content, str) and encrypted_content:
                    encrypted_reasoning_parts.append(encrypted_content)

                for content_entry in item.get("content", []):
                    if not isinstance(content_entry, dict):
                        continue
                    if content_entry.get("type") == "reasoning_text":
                        reasoning_text = content_entry.get("text", "")
                        if reasoning_text:
                            reasoning_content_parts.append(reasoning_text)

            elif item_type == "message":
                for part in item.get("content", []):
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "output_text":
                        text = part.get("text", "")
                        if text:
                            text_parts.append(text)

            elif item_type == "function_call":
                function_calls.append(_parse_function_call(item))

        usage_obj = response_json.get("usage", {})
        input_tokens = int(_usage_value(usage_obj, "input_tokens"))
        output_tokens = int(_usage_value(usage_obj, "output_tokens"))
        input_details = usage_obj.get("input_tokens_details", {})
        output_details = usage_obj.get("output_tokens_details", {})

        cached_input_tokens = (
            int(input_details.get("cached_tokens", 0) or 0)
            if isinstance(input_details, dict)
            else 0
        )
        reasoning_tokens = (
            int(output_details.get("reasoning_tokens", 0) or 0)
            if isinstance(output_details, dict)
            else 0
        )

        reasoning_summary = "\n\n".join(
            part for part in reasoning_summary_parts if part.strip()
        ).strip()
        reasoning_content = "\n\n".join(
            part for part in reasoning_content_parts if part.strip()
        ).strip()
        text = "".join(text_parts).strip()
        if not text:
            output_text = response_json.get("output_text")
            if isinstance(output_text, str):
                text = output_text.strip()

        return CompletedResponse(
            response_id=response_json.get("id"),
            text=text,
            usage=TokenUsage(
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                model=_response_model_name(response_json),
            ),
            function_calls=function_calls,
            reasoning_summary=reasoning_summary,
            reasoning_content=reasoning_content,
            provider_data={
                "encrypted_reasoning_content": encrypted_reasoning_parts,
                "reasoning": response_json.get("reasoning"),
            },
        )


def _build_user_input_item(prompt: str) -> dict[str, Any]:
    return {"role": "user", "content": prompt}


def _build_system_input_item(prompt: str) -> dict[str, Any]:
    return {"role": "system", "content": prompt}


def _extract_reasoning_summary_texts(raw_summary: Any) -> list[str]:
    if not isinstance(raw_summary, list):
        return []

    summary_parts: list[str] = []
    for entry in raw_summary:
        if isinstance(entry, dict):
            if entry.get("type") == "summary_text":
                text = entry.get("text", "")
                if text:
                    summary_parts.append(text)
        elif isinstance(entry, str) and entry:
            summary_parts.append(entry)
    return summary_parts


def _parse_function_call(item: dict[str, Any]) -> ToolCall:
    raw_args = item.get("arguments", "")
    arguments: dict[str, Any] | str | None
    if isinstance(raw_args, str):
        try:
            arguments = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            arguments = raw_args
    else:
        arguments = raw_args

    return ToolCall(
        call_id=str(item.get("call_id", "")),
        name=str(item.get("name", "")),
        arguments=arguments,
    )


def _find_by_id(calls: list[ToolCall], call_id: str) -> ToolCall | None:
    for call in calls:
        if call.call_id == call_id:
            return call
    return None


def _response_include(model: str) -> list[str]:
    if any(model.startswith(prefix) for prefix in _ENCRYPTED_REASONING_MODELS):
        return ["reasoning.encrypted_content"]
    return []


def _reasoning_request(model: str, effort: str) -> dict[str, Any]:
    if any(model.startswith(prefix) for prefix in _REASONING_EFFORT_MODELS):
        return {"effort": _EFFORT_MAP.get(effort, "high")}
    return {}


def _usage_value(usage_obj: Any, key: str) -> int:
    if not isinstance(usage_obj, dict):
        return 0
    return int(usage_obj.get(key, 0) or 0)


def _response_model_name(response_json: dict[str, Any]) -> str:
    model = response_json.get("model")
    return model if isinstance(model, str) else ""


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _normalize_http_error(
    exc: urllib.error.HTTPError,
    error_body: str,
) -> dict[str, Any]:
    payload = _parse_error_payload(error_body)
    error_type = _HTTP_ERROR_TYPES.get(exc.code)
    message = _HTTP_ERROR_MESSAGES.get(exc.code, f"HTTP {exc.code}")
    request_id = _request_id_from_headers(exc)

    if payload is not None:
        payload_request_id = payload.get("request_id")
        if isinstance(payload_request_id, str) and payload_request_id.strip():
            request_id = payload_request_id.strip()

        error_value = payload.get("error")
        if isinstance(error_value, dict):
            payload_type = error_value.get("type")
            if isinstance(payload_type, str) and payload_type.strip():
                error_type = payload_type.strip()
            payload_message = error_value.get("message")
            if isinstance(payload_message, str) and payload_message.strip():
                message = payload_message.strip()
        elif isinstance(error_value, str) and error_value.strip():
            message = error_value.strip()

    if error_type is None:
        if 400 <= exc.code < 500:
            error_type = "invalid_request_error"
        else:
            error_type = "api_error"

    return {
        "type": "error",
        "status": exc.code,
        "error": {
            "type": error_type,
            "message": message,
        },
        **({"request_id": request_id} if request_id else {}),
    }


def _parse_error_payload(error_body: str) -> dict[str, Any] | None:
    stripped = error_body.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _request_id_from_headers(exc: urllib.error.HTTPError) -> str | None:
    if not exc.headers:
        return None
    for header_name in ("request-id", "x-request-id"):
        request_id = exc.headers.get(header_name)
        if isinstance(request_id, str) and request_id.strip():
            return request_id.strip()
    return None


def _format_error_message(prefix: str, error_payload: dict[str, Any]) -> str:
    return f"{prefix}: {json.dumps(error_payload, sort_keys=True)}"


def _extract_retry_after(exc: urllib.error.HTTPError, attempt: int) -> float:
    try:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            return max(0.1, min(float(retry_after), 60.0)) + 1.0
    except (TypeError, ValueError):
        pass
    return min(2.0 * (2**attempt), 30.0) + 1.0


def _waiting_message_for_input_items(input_items: list[dict[str, Any]]) -> str:
    has_user_message = any(
        isinstance(item, dict) and item.get("role") == "user" for item in input_items
    )
    if has_user_message:
        return "analyzing your request..."

    has_tool_output = any(
        isinstance(item, dict) and item.get("type") == "function_call_output"
        for item in input_items
    )
    if has_tool_output:
        return "integrating tool results..."

    return "processing..."


def _reasoning_body_text(reasoning_text: str, summary_text: str) -> str | None:
    if reasoning_text.strip():
        return reasoning_text
    body = _summary_body_text(summary_text)
    return body if body.strip() else None


def _summary_body_text(summary_text: str) -> str:
    lines = summary_text.splitlines()
    first_non_empty_index = next(
        (idx for idx, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_non_empty_index is None:
        return ""
    remaining_non_empty = any(
        line.strip() for line in lines[first_non_empty_index + 1 :]
    )
    if not remaining_non_empty:
        return ""
    return "\n".join(lines[first_non_empty_index + 1 :]).lstrip("\r\n")
