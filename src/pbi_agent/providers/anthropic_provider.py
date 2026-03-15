"""Anthropic Messages API provider.

Uses direct HTTP calls (``urllib.request``) to the Anthropic Messages API.
Conversation history is managed client-side by maintaining a full
``messages`` list that is sent with every request.

All tools (including shell and apply_patch) are registered function tools
— no provider-specific native tool types.
"""

from __future__ import annotations
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import execute_tool_calls as _execute_tool_calls
from pbi_agent.config import Settings
from pbi_agent.models.messages import CompletedResponse, TokenUsage, ToolCall
from pbi_agent.providers.base import Provider
from pbi_agent.tools.registry import get_anthropic_tool_definitions
from pbi_agent.tools.types import ToolContext
from pbi_agent.ui.display_protocol import DisplayProtocol

_log = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Map the CLI reasoning-effort values to Anthropic adaptive thinking effort.
_EFFORT_MAP: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "max",
}

_HTTP_ERROR_TYPES: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    413: "request_too_large",
    429: "rate_limit_error",
    500: "api_error",
    529: "overloaded_error",
}

_HTTP_ERROR_MESSAGES: dict[int, str] = {
    400: "There was an issue with the format or content of your request.",
    401: "There's an issue with your API key.",
    403: "Your API key does not have permission to use the specified resource.",
    404: "The requested resource could not be found.",
    413: "Request exceeds the maximum allowed number of bytes.",
    429: "Your account has hit a rate limit.",
    500: "An unexpected error has occurred internal to Anthropic's systems.",
    529: "The API is temporarily overloaded.",
}


class AnthropicProvider(Provider):
    """Provider backed by the Anthropic Messages HTTP API."""

    def __init__(
        self,
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
    ) -> None:
        self._settings = settings
        self._tools = get_anthropic_tool_definitions(excluded_names=excluded_tools)
        self._system_prompt = system_prompt or get_system_prompt()
        # Client-side conversation history — full messages list.
        self._messages: list[dict[str, Any]] = []

    @property
    def settings(self) -> Settings:
        return self._settings

    # -- lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        # HTTP is stateless; nothing to connect.  We validate the API key
        # eagerly so errors surface early.
        if not self._settings.api_key:
            raise ValueError(
                "Missing API key. Set PBI_AGENT_API_KEY in environment or pass "
                "--api-key."
            )

    def close(self) -> None:
        pass

    def reset_conversation(self) -> None:
        self._messages.clear()

    # -- request_turn --------------------------------------------------------

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
        # Build the new message to append to history.
        if user_message is not None:
            self._messages.append(
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_message}],
                }
            )
        elif tool_result_items is not None:
            # Tool results are sent as a user message containing tool_result
            # content blocks.
            self._messages.append(
                {
                    "role": "user",
                    "content": tool_result_items,
                }
            )
        else:
            raise ValueError("Either user_message or tool_result_items is required")

        system_prompt = instructions or self._system_prompt

        response = self._http_request(
            system_prompt=system_prompt,
            display=display,
        )
        session_usage.add(response.usage)
        turn_usage.add(response.usage)
        display.session_usage(session_usage)
        return response

    # -- execute_tool_calls --------------------------------------------------

    def execute_tool_calls(
        self,
        response: CompletedResponse,
        *,
        max_workers: int,
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        sub_agent_depth: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Execute all tool calls in the response.

        All ``tool_use`` content blocks are routed through the registered
        function tool handlers via ``tool_runtime.execute_tool_calls``.
        """
        # The raw content blocks are stored in provider_data.
        pdata = response.provider_data or {}
        content_blocks: list[dict[str, Any]] = (
            pdata.get("content_blocks", []) if isinstance(pdata, dict) else pdata
        )
        tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]

        if not tool_use_blocks:
            return [], False

        # Convert Anthropic tool_use blocks to ToolCall objects so we can
        # reuse the existing tool_runtime.
        fn_calls = [
            ToolCall(
                call_id=b.get("id", ""),
                name=b.get("name", ""),
                arguments=b.get("input"),
            )
            for b in tool_use_blocks
        ]

        displayable_calls = [call for call in fn_calls if call.name != "sub_agent"]
        if displayable_calls:
            display.function_start(len(displayable_calls))
        batch = _execute_tool_calls(
            fn_calls,
            max_workers=max_workers,
            context=ToolContext(
                settings=self._settings,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                sub_agent_depth=sub_agent_depth,
            ),
        )
        had_errors = batch.had_errors

        tool_result_items: list[dict[str, Any]] = []
        for result in batch.results:
            call = _find_by_id(fn_calls, result.call_id)
            if not (call and call.name == "sub_agent"):
                display.function_result(
                    name=call.name if call else "unknown",
                    success=not result.is_error,
                    call_id=result.call_id,
                    arguments=call.arguments if call else None,
                )
            tool_result_items.append(
                {
                    "type": "tool_result",
                    "tool_use_id": result.call_id,
                    "content": result.output_json,
                    **({"is_error": True} if result.is_error else {}),
                }
            )
        if displayable_calls:
            display.tool_group_end()

        return tool_result_items, had_errors

    # -- HTTP transport ------------------------------------------------------

    def _http_request(
        self,
        *,
        system_prompt: str | None,
        display: DisplayProtocol,
    ) -> CompletedResponse:
        """Send the current messages to the Anthropic Messages API and return
        a parsed ``CompletedResponse``."""
        display.wait_start("waiting for Anthropic response...")

        body: dict[str, Any] = {
            "model": self._settings.model,
            "max_tokens": self._settings.max_tokens,
            "cache_control": {"type": "ephemeral"},
            "tools": self._tools,
            "messages": self._messages,
            "thinking": {"type": "adaptive"},
        }

        # Map reasoning-effort to Anthropic effort level.
        effort = _EFFORT_MAP.get(self._settings.reasoning_effort, "high")
        body["output_config"] = {"effort": effort}

        if system_prompt:
            body["system"] = system_prompt

        request_data = json.dumps(body).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._settings.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }

        max_retries = self._settings.max_retries
        last_error: Exception | None = None
        last_error_message: str | None = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                display.retry_notice(attempt, max_retries)

            try:
                req = urllib.request.Request(
                    ANTHROPIC_API_URL,
                    data=request_data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=300) as resp:
                    response_bytes = resp.read()
                    response_json = json.loads(response_bytes.decode("utf-8"))

                result = self._parse_response(response_json)
                display.wait_stop()

                # Render thinking blocks (if any) before the main text.
                pdata = result.provider_data or {}
                if isinstance(pdata, dict):
                    for thinking_text in pdata.get("thinking_parts", []):
                        display.render_thinking(thinking_text)
                    if pdata.get("has_redacted_thinking"):
                        display.render_redacted_thinking()

                # Render the text in one shot (no streaming).
                if result.text:
                    display.render_markdown(result.text)

                # Append the assistant's response to conversation history so
                # subsequent turns include it.
                self._messages.append(
                    {
                        "role": "assistant",
                        "content": response_json.get("content", []),
                    }
                )

                return result

            except urllib.error.HTTPError as exc:
                error_body = _read_error_body(exc)
                error_payload = _normalize_http_error(exc, error_body)

                # Rate limiting
                if exc.code == 429:
                    if attempt >= max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            _format_error_message(
                                f"Anthropic rate limit exceeded after {max_retries + 1} attempts",
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

                # Overloaded (529)
                if exc.code == 529:
                    if attempt >= max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            _format_error_message(
                                f"Anthropic API overloaded after {max_retries + 1} attempts",
                                error_payload,
                            )
                        ) from exc
                    wait = min(2.0 * (2**attempt), 30.0) + 1.0
                    display.overload_notice(
                        wait_seconds=wait,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    time.sleep(wait)
                    continue

                # Server errors (5xx) — retry
                if exc.code >= 500:
                    last_error = exc
                    last_error_message = _format_error_message(
                        f"Anthropic request failed after {max_retries + 1} attempts",
                        error_payload,
                    )
                    continue

                # Client errors (4xx) — don't retry
                display.wait_stop()
                raise RuntimeError(
                    _format_error_message(
                        f"Anthropic API error {exc.code}",
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
                f"Anthropic request failed after {max_retries + 1} attempts: "
                f"{last_error}"
            ) from last_error
        raise RuntimeError("Anthropic request failed after retries.")

    # -- response parsing ----------------------------------------------------

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        """Parse an Anthropic Messages API response into a CompletedResponse."""
        content_blocks: list[dict[str, Any]] = response_json.get("content", [])

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        has_redacted_thinking: bool = False
        function_calls: list[ToolCall] = []

        for block in content_blocks:
            block_type = block.get("type")

            if block_type == "thinking":
                thinking_text = block.get("thinking", "")
                if thinking_text:
                    thinking_parts.append(thinking_text)

            elif block_type == "redacted_thinking":
                has_redacted_thinking = True

            elif block_type == "text":
                text = block.get("text", "")
                if text:
                    text_parts.append(text)

            elif block_type == "tool_use":
                name = block.get("name", "")
                function_calls.append(
                    ToolCall(
                        call_id=block.get("id", ""),
                        name=name,
                        arguments=block.get("input"),
                    )
                )

        # Parse usage
        usage_obj = response_json.get("usage", {})
        base_input_tokens = int(usage_obj.get("input_tokens", 0) or 0)
        output_tokens = int(usage_obj.get("output_tokens", 0) or 0)
        cache_read_tokens = int(usage_obj.get("cache_read_input_tokens", 0) or 0)
        cache_creation_tokens = int(
            usage_obj.get("cache_creation_input_tokens", 0) or 0
        )

        # Break down cache creation by TTL (default is 5-minute).
        cache_creation_obj = usage_obj.get("cache_creation", {})
        if isinstance(cache_creation_obj, dict):
            cache_1h = int(cache_creation_obj.get("ephemeral_1h_input_tokens", 0) or 0)
        else:
            cache_1h = 0
        cache_5m = max(cache_creation_tokens - cache_1h, 0)

        # Total input for display (base + cache reads + cache writes).
        total_input = base_input_tokens + cache_read_tokens + cache_creation_tokens

        return CompletedResponse(
            response_id=response_json.get("id"),
            text="\n\n".join(text_parts).strip(),
            usage=TokenUsage(
                input_tokens=total_input,
                cached_input_tokens=cache_read_tokens,
                cache_write_tokens=cache_5m,
                cache_write_1h_tokens=cache_1h,
                output_tokens=output_tokens,
                context_tokens=total_input + output_tokens,
            ),
            function_calls=function_calls,
            # Store raw content blocks so execute_tool_calls can access the
            # full tool_use data (including input parameters), plus parsed
            # thinking data for display.
            provider_data={
                "content_blocks": content_blocks,
                "thinking_parts": thinking_parts,
                "has_redacted_thinking": has_redacted_thinking,
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_by_id(calls: list[ToolCall], call_id: str) -> ToolCall | None:
    for c in calls:
        if c.call_id == call_id:
            return c
    return None


def _extract_retry_after(exc: urllib.error.HTTPError, attempt: int) -> float:
    """Extract retry wait from Retry-After header or use exponential backoff."""
    try:
        retry_header = exc.headers.get("Retry-After") if exc.headers else None
        if retry_header:
            return max(0.1, min(float(retry_header), 60.0)) + 1.0
    except (ValueError, TypeError):
        pass
    return min(2.0 * (2**attempt), 30.0) + 1.0


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
    request_id = exc.headers.get("request-id")
    if isinstance(request_id, str) and request_id.strip():
        return request_id.strip()
    return None


def _format_error_message(prefix: str, error_payload: dict[str, Any]) -> str:
    return f"{prefix}: {json.dumps(error_payload, sort_keys=True)}"
