"""Generic OpenAI-compatible Chat Completions HTTP provider.

Designed for OpenAI-compatible gateways (for example OpenRouter) that expose
an OpenAI Chat Completions compatible API.
"""

from __future__ import annotations
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from pbi_agent import __version__
from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import execute_tool_calls as _execute_tool_calls
from pbi_agent.config import Settings
from pbi_agent.models.messages import CompletedResponse, TokenUsage, ToolCall
from pbi_agent.providers.base import Provider
from pbi_agent.tools.registry import get_openai_chat_tool_definitions
from pbi_agent.ui.display_protocol import DisplayProtocol

_log = logging.getLogger(__name__)


class GenericProvider(Provider):
    """Provider backed by OpenAI Chat Completions compatible HTTP APIs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tools = get_openai_chat_tool_definitions()
        self._system_prompt = get_system_prompt()
        self._messages: list[dict[str, Any]] = []

    def connect(self) -> None:
        if not self._settings.api_key:
            raise ValueError(
                "Missing API key. Set PBI_AGENT_API_KEY in environment or pass "
                "--api-key."
            )

    def close(self) -> None:
        pass

    def reset_conversation(self) -> None:
        self._messages.clear()

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
            self._messages.append({"role": "user", "content": user_message})
        elif tool_result_items is not None:
            self._messages.extend(tool_result_items)
        else:
            raise ValueError("Either user_message or tool_result_items is required")

        result = self._http_request(
            instructions=instructions or self._system_prompt,
            display=display,
        )
        session_usage.add(result.usage)
        turn_usage.add(result.usage)
        display.session_usage(session_usage)

        assistant_message = result.provider_data.get("assistant_message")
        if isinstance(assistant_message, dict):
            self._messages.append(assistant_message)

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

        tool_result_items: list[dict[str, Any]] = []
        for result in batch.results:
            call = _find_by_id(response.function_calls, result.call_id)
            display.function_result(
                name=call.name if call else "unknown",
                success=not result.is_error,
                call_id=result.call_id,
                arguments=call.arguments if call else None,
            )
            tool_result_items.append(
                {
                    "role": "tool",
                    "tool_call_id": result.call_id,
                    "content": result.output_json,
                }
            )
        display.tool_group_end()
        return tool_result_items, batch.had_errors

    def _http_request(
        self,
        *,
        instructions: str,
        display: DisplayProtocol,
    ) -> CompletedResponse:
        display.wait_start("waiting for generic provider response...")

        messages: list[dict[str, Any]] = [{"role": "system", "content": instructions}]
        messages.extend(self._messages)

        body: dict[str, Any] = {
            "messages": messages,
            "tools": self._tools,
            "tool_choice": "auto",
            "max_tokens": self._settings.max_tokens,
        }
        if _should_send_model(self._settings):
            body["model"] = self._settings.model

        request_data = json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._settings.api_key}",
            "User-Agent": f"pbi-agent/{__version__}",
        }

        max_retries = self._settings.max_retries
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                display.retry_notice(attempt, max_retries)

            try:
                req = urllib.request.Request(
                    self._settings.generic_api_url,
                    data=request_data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=300) as resp:
                    response_json = json.loads(resp.read().decode("utf-8"))

                result = self._parse_response(response_json)
                display.wait_stop()

                if result.text:
                    display.render_markdown(result.text)

                return result
            except urllib.error.HTTPError as exc:
                error_body = ""
                try:
                    error_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                if exc.code == 429:
                    if attempt >= max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            f"Generic provider rate limit exceeded after {max_retries + 1} "
                            f"attempts: {error_body}"
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
                    continue

                display.wait_stop()
                raise RuntimeError(
                    f"Generic provider API error {exc.code}: {error_body}"
                ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                continue

        display.wait_stop()
        if last_error is not None:
            raise RuntimeError(
                f"Generic provider request failed after {max_retries + 1} attempts: "
                f"{last_error}"
            ) from last_error
        raise RuntimeError("Generic provider request failed after retries.")

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        choices = response_json.get("choices", [])
        first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = first_choice.get("message", {})
        if not isinstance(message, dict):
            message = {}

        text = _extract_message_text(message.get("content"))

        function_calls = _parse_tool_calls(message.get("tool_calls"))

        usage_obj = response_json.get("usage", {})
        prompt_tokens = int(usage_obj.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage_obj.get("completion_tokens", 0) or 0)
        completion_details = usage_obj.get("completion_tokens_details", {})
        reasoning_tokens = (
            int(completion_details.get("reasoning_tokens", 0) or 0)
            if isinstance(completion_details, dict)
            else 0
        )

        return CompletedResponse(
            response_id=response_json.get("id"),
            text=text,
            usage=TokenUsage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
                model=_response_model_name(response_json),
            ),
            function_calls=function_calls,
            provider_data={"assistant_message": _normalize_assistant_message(message)},
        )


def _find_by_id(calls: list[ToolCall], call_id: str) -> ToolCall | None:
    for call in calls:
        if call.call_id == call_id:
            return call
    return None


def _response_model_name(response_json: dict[str, Any]) -> str:
    model = response_json.get("model")
    return model if isinstance(model, str) else ""


def _should_send_model(settings: Settings) -> bool:
    return bool(settings.model)


def _extract_message_text(content: Any) -> str:
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


def _parse_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
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


def _normalize_message_content(content: Any) -> str | list[dict[str, str]] | None:
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


def _normalize_tool_calls(raw_tool_calls: Any) -> list[dict[str, Any]]:
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


def _extract_retry_after(exc: urllib.error.HTTPError, attempt: int) -> float:
    try:
        retry_header = exc.headers.get("Retry-After") if exc.headers else None
        if retry_header:
            return max(0.1, min(float(retry_header), 60.0)) + 1.0
    except (TypeError, ValueError):
        pass
    return min(2.0 * (2**attempt), 30.0) + 1.0
