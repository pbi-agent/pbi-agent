"""OpenAI Responses WebSocket provider.

Wraps the existing ``ws_client``, ``protocol``, and tool-runtime modules
behind the :class:`Provider` interface.  Conversation history is managed
server-side via ``previous_response_id``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from pbi_agent.agent.protocol import (
    RateLimitError,
    build_response_create_payload,
    parse_completed_response,
    parse_error_event,
)
from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import (
    execute_tool_calls as _execute_tool_calls,
    to_function_call_output_items,
)
from pbi_agent.agent.ws_client import (
    ResponsesWebSocketClient,
    WebSocketClientError,
    WebSocketClientTransientError,
)
from pbi_agent.config import Settings
from pbi_agent.ui import Display
from pbi_agent.models.messages import CompletedResponse, TokenUsage
from pbi_agent.providers.base import Provider
from pbi_agent.tools.registry import get_openai_tool_definitions

_log = logging.getLogger(__name__)
_USAGE_REFRESH_DELAYS_SECS = (0.0, 0.2, 0.5)
_RETRIEVE_TIMEOUT_SECS = 3.0


class OpenAIProvider(Provider):
    """Provider backed by OpenAI's Responses WebSocket API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ws: ResponsesWebSocketClient | None = None
        self._previous_response_id: str | None = None
        self._tools = get_openai_tool_definitions()
        self._instructions = get_system_prompt()
        self._deferred_usage_refresh: dict[str, Any] | None = None
        self._usage_refresh_lock = threading.Lock()
        self._pending_usage_refreshes: list[threading.Event] = []

    # -- lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        if self._ws is not None:
            return
        self._ws = ResponsesWebSocketClient(
            self._settings.ws_url, self._settings.api_key
        )
        self._ws.connect()

    def close(self) -> None:
        if self._ws is not None:
            self._ws.close()
            self._ws = None

    def settle(self, *, timeout_seconds: float = 0.0) -> None:
        if timeout_seconds <= 0:
            return

        deadline = time.monotonic() + timeout_seconds
        while True:
            with self._usage_refresh_lock:
                pending = [
                    evt for evt in self._pending_usage_refreshes if not evt.is_set()
                ]
            if not pending:
                return

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            pending[0].wait(timeout=remaining)

    # -- request_turn --------------------------------------------------------

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        tool_result_items: list[dict[str, Any]] | None = None,
        instructions: str | None = None,
        display: Display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> CompletedResponse:
        assert self._ws is not None, "Provider is not connected"

        if user_message is not None:
            input_items: list[dict[str, Any]] = [_build_user_input_item(user_message)]
        elif tool_result_items is not None:
            input_items = tool_result_items
        else:
            raise ValueError("Either user_message or tool_result_items is required")

        effective_instructions = instructions or self._instructions
        response = self._request_with_retries(
            input_items=input_items,
            instructions=effective_instructions,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
        )
        self._previous_response_id = response.response_id
        return response

    # -- execute_tool_calls --------------------------------------------------

    def execute_tool_calls(
        self,
        response: CompletedResponse,
        *,
        max_workers: int,
        display: Display,
    ) -> tuple[list[dict[str, Any]], bool]:
        had_errors = False
        output_items: list[dict[str, Any]] = []

        # --- function calls ------------------------------------------------
        if response.function_calls:
            display.function_start(len(response.function_calls))
            function_batch = _execute_tool_calls(
                response.function_calls,
                max_workers=max_workers,
            )
            had_errors = had_errors or function_batch.had_errors
            for result in function_batch.results:
                call = _find_function_call(response.function_calls, result.call_id)
                display.function_result(
                    name=call.name if call else "unknown",
                    success=not result.is_error,
                    call_id=result.call_id,
                    arguments=call.arguments if call else None,
                )
            output_items.extend(to_function_call_output_items(function_batch.results))
            display.tool_group_end()

        return output_items, had_errors

    # -- internal transport --------------------------------------------------

    def _request_with_retries(
        self,
        *,
        input_items: list[dict[str, Any]],
        instructions: str | None,
        display: Display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> CompletedResponse:
        assert self._ws is not None

        payload = build_response_create_payload(
            model=self._settings.model,
            input_items=input_items,
            tools=self._tools,
            previous_response_id=self._previous_response_id,
            store=True,
            instructions=instructions,
            reasoning_effort=self._settings.reasoning_effort,
            compact_threshold=self._settings.compact_threshold,
        )

        max_retries = self._settings.ws_max_retries
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            self._deferred_usage_refresh = None
            if attempt > 0:
                display.retry_notice(attempt, max_retries)
                self._ws.reconnect()
            try:
                self._ws.send_json(payload)
                response = self._read_one_response(
                    stream_output=True,
                    display=display,
                    waiting_message=_waiting_message_for_input_items(input_items),
                )
                session_usage.add(response.usage)
                turn_usage.add(response.usage)
                display.session_usage(session_usage)
                self._start_deferred_usage_refresh(
                    display=display,
                    session_usage=session_usage,
                    turn_usage=turn_usage,
                )
                return response
            except RateLimitError as exc:
                if attempt >= max_retries:
                    raise
                wait_seconds = _rate_limit_wait(exc, attempt)
                display.rate_limit_notice(
                    wait_seconds=wait_seconds,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )
                time.sleep(wait_seconds)
                continue
            except WebSocketClientTransientError as exc:
                last_error = exc
                continue
            except WebSocketClientError:
                raise

        if last_error is not None:
            raise WebSocketClientError(str(last_error)) from last_error
        raise WebSocketClientError("WebSocket request failed after retries.")

    def _read_one_response(
        self,
        *,
        stream_output: bool,
        display: Display,
        waiting_message: str,
    ) -> CompletedResponse:
        assert self._ws is not None

        streamed_text_parts: list[str] = []
        streamed_summary_parts: list[str] = []
        streamed_reasoning_parts: list[str] = []
        thinking_widget_id: str | None = None
        if stream_output:
            display.wait_start(waiting_message)

        try:
            while True:
                event = self._ws.recv_json()
                event_type = event.get("type")

                if event_type == "response.reasoning_summary_text.delta":
                    delta = event.get("delta", "")
                    if delta:
                        streamed_summary_parts.append(delta)
                elif event_type == "response.reasoning_summary_text.done":
                    summary_text = "".join(streamed_summary_parts)
                    if summary_text.strip() and stream_output:
                        thinking_widget_id = display.render_thinking(
                            _reasoning_body_text("", summary_text),
                            title=summary_text,
                            replace_existing=True,
                            widget_id=thinking_widget_id,
                        )
                elif event_type == "response.reasoning_text.delta":
                    delta = event.get("delta", "")
                    if delta:
                        streamed_reasoning_parts.append(delta)
                        summary_text = "".join(streamed_summary_parts)
                        if summary_text.strip() and stream_output:
                            thinking_widget_id = display.render_thinking(
                                _reasoning_body_text(
                                    "".join(streamed_reasoning_parts),
                                    summary_text,
                                ),
                                title=summary_text,
                                replace_existing=True,
                                widget_id=thinking_widget_id,
                            )
                elif event_type == "response.reasoning_text.done":
                    summary_text = "".join(streamed_summary_parts)
                    reasoning_text = "".join(streamed_reasoning_parts)
                    if summary_text.strip() and stream_output:
                        thinking_widget_id = display.render_thinking(
                            _reasoning_body_text(reasoning_text, summary_text),
                            title=summary_text,
                            replace_existing=True,
                            widget_id=thinking_widget_id,
                        )
                elif event_type == "response.output_text.delta":
                    delta = event.get("delta", "")
                    if delta:
                        streamed_text_parts.append(delta)
                        if stream_output:
                            display.stream_delta(delta)
                elif event_type == "response.completed":
                    response_obj = event.get("response", {})
                    if not isinstance(response_obj, dict):
                        response_obj = {}
                    response = parse_completed_response(
                        response_obj, streamed_text_parts
                    )
                    streamed_summary_text = "".join(streamed_summary_parts)
                    if not response.reasoning_summary and streamed_summary_text.strip():
                        response.reasoning_summary = streamed_summary_text
                    streamed_reasoning_text = "".join(streamed_reasoning_parts)
                    if (
                        not response.reasoning_content
                        and streamed_reasoning_text.strip()
                    ):
                        response.reasoning_content = streamed_reasoning_text
                    if stream_output:
                        summary_text = response.reasoning_summary
                        reasoning_text = response.reasoning_content
                        if summary_text.strip() or reasoning_text.strip():
                            thinking_widget_id = display.render_thinking(
                                _reasoning_body_text(reasoning_text, summary_text),
                                title=summary_text or None,
                                replace_existing=True,
                                widget_id=thinking_widget_id,
                            )
                        display.stream_end()
                    self._refresh_usage_if_needed(
                        response,
                        response_obj=response_obj,
                        streamed_text_parts=streamed_text_parts,
                        display=display,
                        thinking_widget_id=thinking_widget_id,
                    )
                    return response
                elif event_type == "error":
                    raise parse_error_event(event)
        except Exception:
            if stream_output:
                display.stream_abort()
            raise

    def _refresh_usage_if_needed(
        self,
        response: CompletedResponse,
        *,
        response_obj: dict[str, Any],
        streamed_text_parts: list[str],
        display: Display,
        thinking_widget_id: str | None,
    ) -> None:
        """Backfill usage when streamed ``response.completed`` reports zeros.

        The streamed completion event can arrive with a zeroed ``usage`` block
        even though the persisted response later contains the final token
        counts. In that case, retrieve the completed response by ID and replace
        only the usage fields if a populated payload becomes available.
        """
        if _has_usage(response.usage):
            return

        response_id = response.response_id
        if not response_id:
            _log.debug("response.completed reported zero usage and omitted response id")
            display.debug("response.completed reported zero usage with no response id")
            return

        _log.debug(
            "response.completed reported zero usage for %s: %s",
            response_id,
            response_obj.get("usage"),
        )
        display.debug(
            f"response.completed reported zero usage for {response_id}; "
            "retrieving final response in background"
        )

        self._deferred_usage_refresh = {
            "response": response,
            "response_id": response_id,
            "initial_usage": response.usage.snapshot(),
            "streamed_text_parts": list(streamed_text_parts),
            "thinking_widget_id": thinking_widget_id,
        }

    def _start_deferred_usage_refresh(
        self,
        *,
        display: Display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> None:
        refresh_request = self._deferred_usage_refresh
        self._deferred_usage_refresh = None
        if not refresh_request:
            return

        refresh_done = threading.Event()
        with self._usage_refresh_lock:
            self._pending_usage_refreshes.append(refresh_done)
        thread = threading.Thread(
            target=self._refresh_usage_background,
            kwargs={
                **refresh_request,
                "display": display,
                "session_usage": session_usage,
                "turn_usage": turn_usage,
                "refresh_done": refresh_done,
            },
            name=f"usage-refresh-{refresh_request['response_id']}",
            daemon=True,
        )
        thread.start()

    def _refresh_usage_background(
        self,
        *,
        response: CompletedResponse,
        response_id: str,
        initial_usage: TokenUsage,
        streamed_text_parts: list[str],
        thinking_widget_id: str | None,
        display: Display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        refresh_done: threading.Event,
    ) -> None:
        try:
            for delay in _USAGE_REFRESH_DELAYS_SECS:
                if delay > 0:
                    time.sleep(delay)

                refreshed_obj = self._retrieve_response_object(response_id)
                if not refreshed_obj:
                    continue

                refreshed = parse_completed_response(refreshed_obj, streamed_text_parts)
                if not _has_usage(refreshed.usage):
                    continue

                usage_delta = _usage_delta(refreshed.usage, initial_usage)
                response.usage = refreshed.usage
                reasoning_updated = False
                if not response.reasoning_summary and refreshed.reasoning_summary:
                    response.reasoning_summary = refreshed.reasoning_summary
                    reasoning_updated = True
                if not response.reasoning_content and refreshed.reasoning_content:
                    response.reasoning_content = refreshed.reasoning_content
                    reasoning_updated = True
                if reasoning_updated:
                    thinking_widget_id = display.render_thinking(
                        _reasoning_body_text(
                            response.reasoning_content,
                            response.reasoning_summary,
                        ),
                        title=response.reasoning_summary or None,
                        widget_id=thinking_widget_id,
                    )
                if _has_usage(usage_delta):
                    session_usage.add(usage_delta)
                    turn_usage.add(usage_delta)
                    display.usage_refresh(session_usage, turn_usage)
                _log.debug(
                    "Recovered usage for %s via responses.retrieve: in=%s out=%s",
                    response_id,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                display.debug(
                    f"recovered usage for {response_id}: "
                    f"{response.usage.total_tokens:,} tokens"
                )
                return
        except Exception:
            _log.debug(
                "responses.retrieve usage refresh failed for %s",
                response_id,
                exc_info=True,
            )
        else:
            _log.debug(
                "responses.retrieve did not yield non-zero usage for %s after retries",
                response_id,
            )
            display.debug(
                f"usage remained unavailable for {response_id} after retrieve retries"
            )
        finally:
            refresh_done.set()
            with self._usage_refresh_lock:
                if refresh_done in self._pending_usage_refreshes:
                    self._pending_usage_refreshes.remove(refresh_done)

    def _retrieve_response_object(self, response_id: str) -> dict[str, Any] | None:
        """Fetch a persisted response object via the HTTPS Responses API."""
        url = _response_retrieve_url(self._settings.responses_url, response_id)
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self._settings.api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=_RETRIEVE_TIMEOUT_SECS) as resp:
                payload = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            _log.debug(
                "responses.retrieve failed for %s with HTTP %s",
                response_id,
                exc.code,
            )
            return None
        except urllib.error.URLError as exc:
            _log.debug("responses.retrieve failed for %s: %s", response_id, exc)
            return None

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            _log.debug("responses.retrieve returned invalid JSON for %s", response_id)
            return None
        return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _build_user_input_item(prompt: str) -> dict[str, Any]:
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": prompt}],
    }


def _find_function_call(calls: list, call_id: str):  # type: ignore[type-arg]
    for c in calls:
        if c.call_id == call_id:
            return c
    return None


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


def _has_usage(usage: TokenUsage) -> bool:
    return any(
        value > 0
        for value in (
            usage.input_tokens,
            usage.cached_input_tokens,
            usage.cache_write_tokens,
            usage.cache_write_1h_tokens,
            usage.output_tokens,
            usage.reasoning_tokens,
        )
    )


def _response_retrieve_url(responses_url: str, response_id: str) -> str:
    parsed = urllib.parse.urlsplit(responses_url)
    path = f"{parsed.path.rstrip('/')}/{urllib.parse.quote(response_id, safe='')}"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)
    )


def _usage_delta(newer: TokenUsage, older: TokenUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=max(newer.input_tokens - older.input_tokens, 0),
        cached_input_tokens=max(
            newer.cached_input_tokens - older.cached_input_tokens,
            0,
        ),
        cache_write_tokens=max(newer.cache_write_tokens - older.cache_write_tokens, 0),
        cache_write_1h_tokens=max(
            newer.cache_write_1h_tokens - older.cache_write_1h_tokens,
            0,
        ),
        output_tokens=max(newer.output_tokens - older.output_tokens, 0),
        reasoning_tokens=max(newer.reasoning_tokens - older.reasoning_tokens, 0),
        model=newer.model or older.model,
    )


def _waiting_message_for_input_items(input_items: list[dict[str, Any]]) -> str:
    item_types = {
        item.get("type")
        for item in input_items
        if isinstance(item, dict) and isinstance(item.get("type"), str)
    }
    if "message" in item_types:
        return "analyzing your request..."
    if "function_call_output" in item_types:
        return "integrating tool results..."
    return "processing..."


def _rate_limit_wait(error: RateLimitError, attempt: int) -> float:
    if error.retry_after_seconds is not None:
        return max(0.1, min(error.retry_after_seconds, 30.0))
    return min(2.0 * (2**attempt), 30.0)
