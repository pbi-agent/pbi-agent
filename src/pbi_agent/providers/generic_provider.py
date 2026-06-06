"""Generic OpenAI-compatible Chat Completions HTTP provider."""

from __future__ import annotations

import time
from typing import Any, TYPE_CHECKING

from pbi_agent.agent.tool_runtime import execute_tool_calls as _execute_tool_calls
from pbi_agent.config import Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import CompletedResponse, TokenUsage, UserTurnInput
from pbi_agent.providers.auth_strategies import (
    ApiKeyHeaderAuth,
    BearerTokenAuth,
    json_model_headers,
)
from pbi_agent.providers.base import Provider
from pbi_agent.providers.endpoints import chat_completions_url
from pbi_agent.providers.protocols.chat_completions import ChatCompletionsProtocol
from pbi_agent.providers.runtime import record_response_usage
from pbi_agent.providers.tool_execution import execute_provider_tool_calls
from pbi_agent.providers.transport import (
    JsonErrorPolicy,
    JsonModelTransport,
    JsonRequestSpec,
    body_error_message,
    parse_json_error_body,
)
from pbi_agent.session_store import MessageRecord
from pbi_agent.tools.availability import default_excluded_tool_names
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.types import ParentContextSnapshot

if TYPE_CHECKING:
    from pbi_agent.observability import RunTracer


class GenericProvider(Provider):
    """Provider backed by OpenAI Chat Completions compatible HTTP APIs."""

    def __init__(
        self,
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> None:
        self._settings = settings
        self._tool_catalog = tool_catalog or ToolCatalog.from_builtin_registry()
        self._excluded_tools = default_excluded_tool_names(excluded_tools)
        self._protocol = ChatCompletionsProtocol(
            settings,
            system_prompt=system_prompt,
            excluded_tools=self._excluded_tools,
            tool_catalog=self._tool_catalog,
        )
        self._transport = JsonModelTransport()

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def _tools(self) -> list[dict[str, Any]]:
        return self._protocol.tools

    @property
    def _messages(self) -> list[dict[str, Any]]:
        return self._protocol.messages

    @property
    def _system_prompt(self) -> str:
        return self._protocol.system_prompt

    def connect(self) -> None:
        if not self._settings.api_key:
            raise ValueError(
                "Missing API key. Set PBI_AGENT_API_KEY in environment or pass "
                "--api-key."
            )

    def close(self) -> None:
        pass

    def reset_conversation(self) -> None:
        self._protocol.reset_conversation()

    def set_system_prompt(self, system_prompt: str) -> None:
        self._protocol.set_system_prompt(system_prompt)

    def refresh_tools(self) -> None:
        if hasattr(self, "_protocol"):
            self._protocol.refresh_tools()

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        self._protocol.restore_messages(messages)

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        self._protocol.restore_history_items(items)

    def set_runtime_settings(self, settings: Settings) -> None:
        if self._settings == settings:
            return
        self._settings = settings
        self._protocol.set_runtime_settings(settings)

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        user_input: UserTurnInput | None = None,
        tool_result_items: list[dict[str, Any]] | None = None,
        instructions: str | None = None,
        session_id: str | None = None,
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        del session_id
        input_value = self._protocol.accept_turn(
            user_message=user_message,
            user_input=user_input,
            tool_result_items=tool_result_items,
        )
        result = self._http_request(
            input_value=input_value,
            instructions=instructions or self._protocol.system_prompt,
            display=display,
            tracer=tracer,
        )
        record_response_usage(
            result,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
        )
        self._protocol.record_response(result)
        self._protocol.render_response(display, result)
        return result

    def execute_tool_calls(
        self,
        response: CompletedResponse,
        *,
        max_workers: int,
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        sub_agent_depth: int = 0,
        parent_context: ParentContextSnapshot | None = None,
        tracer: "RunTracer | None" = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        return execute_provider_tool_calls(
            response.function_calls,
            max_workers=max_workers,
            settings=self._settings,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            tool_catalog=self._tool_catalog,
            excluded_tools=self._excluded_tools,
            serialize_result=self._protocol.serialize_tool_result,
            sub_agent_depth=sub_agent_depth,
            parent_context=parent_context,
            tracer=tracer,
            tool_availability_overridden=getattr(
                self, "_tool_availability_overridden", False
            ),
            workspace_root=getattr(self, "_workspace_root", None),
            workspace_directory_key=getattr(self, "_workspace_directory_key", None),
            execute_calls=_execute_tool_calls,
        )

    def _http_request(
        self,
        *,
        input_value: str | list[dict[str, Any]],
        instructions: str,
        display: DisplayProtocol,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        url = chat_completions_url(self._settings)
        body = self._protocol.build_request_body(instructions=instructions)
        headers = json_model_headers()
        if self._settings.provider == "azure":
            headers.update(
                ApiKeyHeaderAuth(self._settings.api_key, "api-key").headers()
            )
        else:
            headers.update(BearerTokenAuth(self._settings.api_key).headers())

        return self._transport.post(
            JsonRequestSpec(
                provider=self._settings.provider,
                model=self._settings.model,
                url=url,
                headers=headers,
                body=body,
                request_config=self._settings.redacted(),
                wait_input=input_value,
                timeout=300,
                error_policy=JsonErrorPolicy(
                    api_error_label="Generic provider API error",
                    rate_limit_exhausted_label="Generic provider rate limit exceeded",
                    overload_exhausted_label="Generic provider API overloaded",
                    request_failed_label="Generic provider request failed",
                    normalize_http_error=parse_json_error_body,
                    format_error=body_error_message,
                    retryable_http_final_uses_error_message=False,
                ),
                sleep=time.sleep,
            ),
            settings=self._settings,
            display=display,
            tracer=tracer,
            parse_response=self._protocol.parse_response,
        )

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        return self._protocol.parse_response(response_json)
