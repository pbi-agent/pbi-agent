"""Google Cloud Vertex AI provider wrapper.

This provider introduces the Google Cloud runtime kind and routes to
provider-shape boundaries. Gemini ``generateContent``, OpenAI-compatible
Chat Completions, OpenAI-compatible Responses, and Anthropic Messages are
implemented here.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, ClassVar, Literal, NoReturn, cast

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import execute_tool_calls as _execute_tool_calls
from pbi_agent.config import Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    ToolCall,
    UserTurnInput,
    WebSearchSource,
)
from pbi_agent.providers.auth_strategies import (
    GoogleGcpAuth,
    google_gcp_auth,
    json_model_headers,
)
from pbi_agent.providers.base import Provider
from pbi_agent.providers.endpoints import (
    GoogleGcpEndpointShape,
    google_gcp_endpoint_url,
    google_gcp_express_endpoint_url,
)
from pbi_agent.providers.protocols.chat_completions import ChatCompletionsProtocol
from pbi_agent.providers.protocols.gemini_generate_content import (
    GeminiGenerateContentProtocol,
)
from pbi_agent.providers.protocols.anthropic_messages import (
    normalize_http_error as normalize_anthropic_http_error,
    render_messages_response,
)
from pbi_agent.providers.protocols.openai_responses import (
    render_responses_display,
    response_history_item_for_input,
    serialize_function_call_output,
)
from pbi_agent.providers.runtime import record_response_usage
from pbi_agent.providers.tool_execution import execute_provider_tool_calls
from pbi_agent.providers.transport import (
    JsonErrorPolicy,
    JsonModelTransport,
    JsonRequestSpec,
    json_error_message,
    parse_json_error_body,
)
from pbi_agent.session_store import MessageRecord
from pbi_agent.tools.availability import (
    default_excluded_tool_names,
    effective_excluded_tool_names,
)
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.types import ParentContextSnapshot, ToolResult
from pbi_agent.web.uploads import load_uploaded_image

if TYPE_CHECKING:
    from pbi_agent.observability import RunTracer

GoogleGcpShapeName = Literal[
    "gemini_generate_content",
    "openai_chat_completions",
    "openai_responses",
    "anthropic_messages",
]

GOOGLE_GCP_SHAPES: tuple[GoogleGcpShapeName, ...] = (
    "gemini_generate_content",
    "openai_chat_completions",
    "openai_responses",
    "anthropic_messages",
)
GOOGLE_GCP_SHAPE_ENV = "PBI_AGENT_GOOGLE_GCP_SHAPE"
_REQUEST_TIMEOUT_SECS = 3600.0
_VERTEX_ANTHROPIC_VERSION = "vertex-2023-10-16"


class GoogleGcpProvider(Provider):
    """Provider wrapper for Google Cloud Vertex AI model shapes."""

    def __init__(
        self,
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
        access_token_resolver: Callable[[], str] | None = None,
    ) -> None:
        self._settings = settings
        self._tool_catalog = tool_catalog or ToolCatalog.from_builtin_registry()
        self._excluded_tools = default_excluded_tool_names(excluded_tools)
        self._instructions = system_prompt or get_system_prompt(
            settings=self._settings,
            excluded_tools=self._excluded_tools,
        )
        self._access_token_resolver = access_token_resolver
        self._shape = self._build_shape()

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def shape_name(self) -> GoogleGcpShapeName:
        return self._shape.shape_name

    @property
    def endpoint_url(self) -> str:
        return self._shape.endpoint_url

    @property
    def auth_headers(self) -> dict[str, str]:
        return self._shape.headers

    def connect(self) -> None:
        self._shape.connect()

    def close(self) -> None:
        self._shape.close()

    def reset_conversation(self) -> None:
        self._shape.reset_conversation()

    def set_previous_response_id(self, response_id: str | None) -> None:
        self._shape.set_previous_response_id(response_id)

    def get_conversation_checkpoint(self) -> str | None:
        return self._shape.get_conversation_checkpoint()

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        self._shape.restore_messages(messages)

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        self._shape.restore_history_items(items)

    def set_system_prompt(self, system_prompt: str) -> None:
        self._instructions = system_prompt
        self._shape.set_system_prompt(system_prompt)

    def refresh_tools(self) -> None:
        self._shape.refresh_tools()

    def set_runtime_settings(self, settings: Settings) -> None:
        if self._settings == settings:
            return
        self._settings = settings
        if google_gcp_shape_for_model(settings.model) == self._shape.shape_name:
            self._shape.set_runtime_settings(settings)
            self._sync_shape_runtime_context()
            return
        self._shape = self._build_shape()

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
        self._sync_shape_runtime_context()
        return self._shape.request_turn(
            user_message=user_message,
            user_input=user_input,
            tool_result_items=tool_result_items,
            instructions=instructions,
            session_id=session_id,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            tracer=tracer,
        )

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
        self._sync_shape_runtime_context()
        return self._shape.execute_tool_calls(
            response,
            max_workers=max_workers,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            sub_agent_depth=sub_agent_depth,
            parent_context=parent_context,
            tracer=tracer,
        )

    def set_excluded_tools(self, excluded_tools: set[str]) -> None:
        normalized = default_excluded_tool_names(excluded_tools)
        if self._excluded_tools == normalized:
            return
        self._excluded_tools = normalized
        self._shape.set_excluded_tools(normalized)

    def set_tool_availability_overridden(self, overridden: bool) -> None:
        self._tool_availability_overridden = overridden
        self._shape.set_tool_availability_overridden(overridden)

    def _build_shape(self) -> "_GoogleGcpShapeStub":
        shape_name = google_gcp_shape_for_model(self._settings.model)
        shape = _create_google_gcp_shape(
            shape_name,
            settings=self._settings,
            instructions=self._instructions,
            access_token_resolver=self._access_token_resolver,
            tool_catalog=self._tool_catalog,
            excluded_tools=self._excluded_tools,
        )
        self._sync_shape_runtime_context(shape)
        return shape

    def _sync_shape_runtime_context(
        self,
        shape: "_GoogleGcpShapeStub | None" = None,
    ) -> None:
        target = self._shape if shape is None else shape
        target.set_tool_availability_overridden(
            getattr(self, "_tool_availability_overridden", False)
        )
        if hasattr(self, "_workspace_root"):
            setattr(target, "_workspace_root", getattr(self, "_workspace_root"))
        if hasattr(self, "_workspace_directory_key"):
            setattr(
                target,
                "_workspace_directory_key",
                getattr(self, "_workspace_directory_key"),
            )


class _GoogleGcpShapeStub:
    shape_name: ClassVar[GoogleGcpShapeName]

    def __init__(
        self,
        *,
        settings: Settings,
        instructions: str,
        access_token_resolver: Callable[[], str] | None,
        tool_catalog: ToolCatalog,
        excluded_tools: set[str],
    ) -> None:
        self._settings = settings
        self._instructions = instructions
        self._access_token_resolver = access_token_resolver
        self._tool_catalog = tool_catalog
        self._excluded_tools = default_excluded_tool_names(excluded_tools)
        self._tool_availability_overridden = False
        self._endpoint_url = google_gcp_endpoint_url(
            self._settings,
            _endpoint_shape(self.shape_name),
            require_project=False,
        )
        self._headers: dict[str, str] = {}
        self._auth: GoogleGcpAuth | None = None
        self._previous_response_id: str | None = None
        self._restored_messages: list[MessageRecord] = []
        self._restored_history_items: list[dict[str, Any]] = []

    @property
    def endpoint_url(self) -> str:
        return self._endpoint_url

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._headers)

    def connect(self) -> None:
        self._connect(allow_api_key=self._supports_api_key_auth())

    def _connect(self, *, allow_api_key: bool) -> None:
        auth = google_gcp_auth(
            self._settings,
            access_token_resolver=self._access_token_resolver,
            allow_api_key=allow_api_key,
        )
        self._auth = auth
        self._endpoint_url = self._endpoint_url_for_auth(
            auth,
            require_project=True,
        )
        headers = json_model_headers()
        headers.update(auth.headers)
        self._headers = headers

    def close(self) -> None:
        pass

    def reset_conversation(self) -> None:
        self._previous_response_id = None
        self._restored_messages.clear()
        self._restored_history_items.clear()

    def set_previous_response_id(self, response_id: str | None) -> None:
        self._previous_response_id = response_id

    def get_conversation_checkpoint(self) -> str | None:
        return self._previous_response_id

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        self._restored_messages = list(messages)

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        self._restored_history_items = list(items)

    def set_system_prompt(self, system_prompt: str) -> None:
        self._instructions = system_prompt

    def set_runtime_settings(self, settings: Settings) -> None:
        self._settings = settings
        self._endpoint_url = self._endpoint_url_for_settings(require_project=False)
        self._headers = {}
        self._auth = None

    def set_excluded_tools(self, excluded_tools: set[str]) -> None:
        self._excluded_tools = default_excluded_tool_names(excluded_tools)
        self.refresh_tools()

    def set_tool_availability_overridden(self, overridden: bool) -> None:
        self._tool_availability_overridden = overridden

    def refresh_tools(self) -> None:
        pass

    def _supports_api_key_auth(self) -> bool:
        return self.shape_name == "gemini_generate_content"

    def _endpoint_url_for_settings(self, *, require_project: bool) -> str:
        return google_gcp_endpoint_url(
            self._settings,
            _endpoint_shape(self.shape_name),
            require_project=require_project,
        )

    def _endpoint_url_for_auth(
        self,
        auth: GoogleGcpAuth,
        *,
        require_project: bool,
    ) -> str:
        if auth.kind == "api_key" and self.shape_name == "gemini_generate_content":
            return google_gcp_express_endpoint_url(
                self._settings,
                _endpoint_shape(self.shape_name),
            )
        return self._endpoint_url_for_settings(require_project=require_project)

    def _post_with_auth_refresh(
        self,
        transport: JsonModelTransport,
        spec: JsonRequestSpec,
        *,
        display: DisplayProtocol,
        tracer: "RunTracer | None",
        parse_response: Callable[[dict[str, Any]], CompletedResponse],
        semantic_validator: Callable[[dict[str, Any]], None] | None = None,
    ) -> CompletedResponse:
        try:
            return transport.post(
                spec,
                settings=self._settings,
                display=display,
                tracer=tracer,
                parse_response=parse_response,
                semantic_validator=semantic_validator,
            )
        except RuntimeError as exc:
            if self._should_refresh_cached_bearer_after_error(exc):
                self._headers = {}
                self._auth = None
                self.connect()
            elif self._should_retry_with_bearer_after_api_key_error(exc):
                self._headers = {}
                self._auth = None
                self._connect(allow_api_key=False)
            else:
                raise
            return transport.post(
                replace(spec, url=self._endpoint_url, headers=self._headers),
                settings=self._settings,
                display=display,
                tracer=tracer,
                parse_response=parse_response,
                semantic_validator=semantic_validator,
            )

    def _should_refresh_cached_bearer_after_error(self, exc: RuntimeError) -> bool:
        return bool(
            self._auth is not None
            and self._auth.refreshable
            and _is_google_gcp_token_expiry_error(str(exc))
        )

    def _should_retry_with_bearer_after_api_key_error(self, exc: RuntimeError) -> bool:
        return bool(
            self._auth is not None
            and self._auth.kind == "api_key"
            and self.shape_name == "gemini_generate_content"
            and _is_google_gcp_api_key_auth_unsupported_error(str(exc))
        )

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
        del (
            user_message,
            user_input,
            tool_result_items,
            instructions,
            session_id,
            display,
            session_usage,
            turn_usage,
            tracer,
        )
        _raise_shape_not_implemented(self.shape_name)

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
        del (
            response,
            max_workers,
            display,
            session_usage,
            turn_usage,
            sub_agent_depth,
            parent_context,
            tracer,
        )
        _raise_shape_not_implemented(self.shape_name)


class _GeminiGenerateContentShape(_GoogleGcpShapeStub):
    shape_name: ClassVar[GoogleGcpShapeName] = "gemini_generate_content"

    def __init__(
        self,
        *,
        settings: Settings,
        instructions: str,
        access_token_resolver: Callable[[], str] | None,
        tool_catalog: ToolCatalog,
        excluded_tools: set[str],
    ) -> None:
        super().__init__(
            settings=settings,
            instructions=instructions,
            access_token_resolver=access_token_resolver,
            tool_catalog=tool_catalog,
            excluded_tools=excluded_tools,
        )
        self._protocol = GeminiGenerateContentProtocol(
            settings,
            system_prompt=instructions,
            excluded_tools=self._excluded_tools,
            tool_catalog=self._tool_catalog,
        )
        self._transport = JsonModelTransport()

    def reset_conversation(self) -> None:
        super().reset_conversation()
        self._protocol.reset_conversation()

    def set_previous_response_id(self, response_id: str | None) -> None:
        del response_id
        self._previous_response_id = None

    def get_conversation_checkpoint(self) -> str | None:
        return None

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        super().restore_messages(messages)
        self._protocol.restore_messages(messages)

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        super().restore_history_items(items)
        self._protocol.restore_history_items(items)

    def set_system_prompt(self, system_prompt: str) -> None:
        super().set_system_prompt(system_prompt)
        self._protocol.set_system_prompt(system_prompt)

    def set_runtime_settings(self, settings: Settings) -> None:
        super().set_runtime_settings(settings)
        self._protocol.set_runtime_settings(settings)

    def set_excluded_tools(self, excluded_tools: set[str]) -> None:
        self._excluded_tools = default_excluded_tool_names(excluded_tools)
        self._protocol.set_excluded_tools(self._excluded_tools)

    def refresh_tools(self) -> None:
        self._protocol.refresh_tools()

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
        wait_input = self._protocol.accept_turn(
            user_message=user_message,
            user_input=user_input,
            tool_result_items=tool_result_items,
        )
        result = self._http_request(
            wait_input=wait_input,
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
        if not response.function_calls:
            return [], False
        calls_by_id = {call.call_id: call for call in response.function_calls}
        return execute_provider_tool_calls(
            response.function_calls,
            max_workers=max_workers,
            settings=self._settings,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            tool_catalog=self._tool_catalog,
            excluded_tools=self._excluded_tools,
            serialize_result=lambda result: self._protocol.serialize_tool_result(
                result,
                calls_by_id.get(result.call_id),
            ),
            sub_agent_depth=sub_agent_depth,
            parent_context=parent_context,
            tracer=tracer,
            tool_availability_overridden=self._tool_availability_overridden,
            workspace_root=getattr(self, "_workspace_root", None),
            workspace_directory_key=getattr(self, "_workspace_directory_key", None),
            execute_calls=_execute_tool_calls,
        )

    def _http_request(
        self,
        *,
        wait_input: str | list[dict[str, Any]],
        instructions: str,
        display: DisplayProtocol,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        if not self._endpoint_url or not self._headers:
            self.connect()

        return self._post_with_auth_refresh(
            self._transport,
            JsonRequestSpec(
                provider=self._settings.provider,
                model=self._settings.model,
                url=self._endpoint_url,
                headers=self._headers,
                body=self._protocol.build_request_body(instructions=instructions),
                request_config=self._settings.redacted(),
                wait_input=wait_input,
                timeout=_REQUEST_TIMEOUT_SECS,
                error_policy=JsonErrorPolicy(
                    api_error_label="Google GCP Gemini API error",
                    rate_limit_exhausted_label="Google GCP Gemini rate limit exceeded",
                    overload_exhausted_label="Google GCP Gemini API overloaded",
                    request_failed_label="Google GCP Gemini request failed",
                    normalize_http_error=parse_json_error_body,
                    format_error=json_error_message,
                ),
                sleep=time.sleep,
            ),
            display=display,
            tracer=tracer,
            parse_response=self._protocol.parse_response,
        )


class _OpenAIChatCompletionsShape(_GoogleGcpShapeStub):
    shape_name: ClassVar[GoogleGcpShapeName] = "openai_chat_completions"

    def __init__(
        self,
        *,
        settings: Settings,
        instructions: str,
        access_token_resolver: Callable[[], str] | None,
        tool_catalog: ToolCatalog,
        excluded_tools: set[str],
    ) -> None:
        super().__init__(
            settings=settings,
            instructions=instructions,
            access_token_resolver=access_token_resolver,
            tool_catalog=tool_catalog,
            excluded_tools=excluded_tools,
        )
        self._protocol = ChatCompletionsProtocol(
            settings,
            system_prompt=instructions,
            excluded_tools=self._excluded_tools,
            tool_catalog=self._tool_catalog,
        )
        self._transport = JsonModelTransport()

    def reset_conversation(self) -> None:
        super().reset_conversation()
        self._protocol.reset_conversation()

    def set_previous_response_id(self, response_id: str | None) -> None:
        del response_id
        self._previous_response_id = None

    def get_conversation_checkpoint(self) -> str | None:
        return None

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        super().restore_messages(messages)
        self._protocol.restore_messages(messages)

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        super().restore_history_items(items)
        self._protocol.restore_history_items(items)

    def set_system_prompt(self, system_prompt: str) -> None:
        super().set_system_prompt(system_prompt)
        self._protocol.set_system_prompt(system_prompt)

    def set_runtime_settings(self, settings: Settings) -> None:
        super().set_runtime_settings(settings)
        self._protocol.set_runtime_settings(settings)

    def set_excluded_tools(self, excluded_tools: set[str]) -> None:
        self._excluded_tools = default_excluded_tool_names(excluded_tools)
        self._protocol.excluded_tools = self._excluded_tools
        self._protocol.refresh_tools()

    def refresh_tools(self) -> None:
        self._protocol.refresh_tools()

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
            tool_availability_overridden=self._tool_availability_overridden,
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
        if not self._endpoint_url or not self._headers:
            self.connect()

        body = self._protocol.build_request_body(instructions=instructions)
        body["stream"] = False

        return self._post_with_auth_refresh(
            self._transport,
            JsonRequestSpec(
                provider=self._settings.provider,
                model=self._settings.model,
                url=self._endpoint_url,
                headers=self._headers,
                body=body,
                request_config=self._settings.redacted(),
                wait_input=input_value,
                timeout=_REQUEST_TIMEOUT_SECS,
                error_policy=JsonErrorPolicy(
                    api_error_label="Google GCP OpenAI Chat Completions API error",
                    rate_limit_exhausted_label=(
                        "Google GCP OpenAI Chat Completions rate limit exceeded"
                    ),
                    overload_exhausted_label=(
                        "Google GCP OpenAI Chat Completions API overloaded"
                    ),
                    request_failed_label=(
                        "Google GCP OpenAI Chat Completions request failed"
                    ),
                    normalize_http_error=parse_json_error_body,
                    format_error=json_error_message,
                ),
                sleep=time.sleep,
            ),
            display=display,
            tracer=tracer,
            parse_response=self._protocol.parse_response,
        )


class _OpenAIResponsesShape(_GoogleGcpShapeStub):
    shape_name: ClassVar[GoogleGcpShapeName] = "openai_responses"

    def __init__(
        self,
        *,
        settings: Settings,
        instructions: str,
        access_token_resolver: Callable[[], str] | None,
        tool_catalog: ToolCatalog,
        excluded_tools: set[str],
    ) -> None:
        super().__init__(
            settings=settings,
            instructions=instructions,
            access_token_resolver=access_token_resolver,
            tool_catalog=tool_catalog,
            excluded_tools=excluded_tools,
        )
        self._transport = JsonModelTransport()
        self._tools: list[dict[str, Any]] = []
        self._input_history_items: list[dict[str, Any]] = []
        self.refresh_tools()

    def reset_conversation(self) -> None:
        super().reset_conversation()
        self._input_history_items.clear()

    def set_previous_response_id(self, response_id: str | None) -> None:
        del response_id
        self._previous_response_id = None

    def get_conversation_checkpoint(self) -> str | None:
        return None

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        super().restore_messages(messages)
        self._input_history_items = [
            {"role": message.role, "content": message.content}
            for message in messages
            if message.role in {"user", "assistant"} and message.content
        ]

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        super().restore_history_items(items)
        self._input_history_items = _openai_responses_history_items_to_input_items(
            items
        )

    def set_excluded_tools(self, excluded_tools: set[str]) -> None:
        self._excluded_tools = default_excluded_tool_names(excluded_tools)
        self.refresh_tools()

    def set_runtime_settings(self, settings: Settings) -> None:
        super().set_runtime_settings(settings)
        self.refresh_tools()

    def refresh_tools(self) -> None:
        excluded_tools = effective_excluded_tool_names(
            self._settings, self._excluded_tools
        )
        self._tools = _google_gcp_openai_responses_tools(
            self._tool_catalog.get_openai_tool_definitions(
                excluded_names=excluded_tools
            )
        )

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
        _input_items, wait_input, simple_prompt = self._accept_turn(
            user_message=user_message,
            user_input=user_input,
            tool_result_items=tool_result_items,
        )
        result = self._http_request(
            wait_input=wait_input,
            simple_prompt=simple_prompt,
            instructions=instructions or self._instructions,
            display=display,
            tracer=tracer,
        )
        record_response_usage(
            result,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
        )
        self._record_response(result)
        render_responses_display(display, result)
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
        if not response.function_calls:
            return [], False

        return execute_provider_tool_calls(
            response.function_calls,
            max_workers=max_workers,
            settings=self._settings,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            tool_catalog=self._tool_catalog,
            excluded_tools=self._excluded_tools,
            serialize_result=serialize_function_call_output,
            sub_agent_depth=sub_agent_depth,
            parent_context=parent_context,
            tracer=tracer,
            tool_availability_overridden=self._tool_availability_overridden,
            workspace_root=getattr(self, "_workspace_root", None),
            workspace_directory_key=getattr(self, "_workspace_directory_key", None),
            execute_calls=_execute_tool_calls,
        )

    def _accept_turn(
        self,
        *,
        user_message: str | None,
        user_input: UserTurnInput | None,
        tool_result_items: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], str | list[dict[str, Any]], str | None]:
        had_history = bool(self._input_history_items)
        if user_input is None and user_message is not None:
            user_input = UserTurnInput(text=user_message)

        if user_input is not None:
            if user_input.images:
                raise ValueError(
                    "Google GCP xAI Responses image inputs are not enabled "
                    "in this build."
                )
            input_items = [_openai_responses_user_input_item(user_input.text)]
            wait_input: str | list[dict[str, Any]] = user_input.text
            simple_prompt = user_input.text if not had_history else None
        elif tool_result_items is not None:
            input_items = [_clone_json_dict(item) for item in tool_result_items]
            wait_input = input_items
            simple_prompt = None
        else:
            raise ValueError("Either user_input or tool_result_items is required")

        self._input_history_items.extend(_clone_json_dict(item) for item in input_items)
        return input_items, wait_input, simple_prompt

    def _http_request(
        self,
        *,
        wait_input: str | list[dict[str, Any]],
        simple_prompt: str | None,
        instructions: str,
        display: DisplayProtocol,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        if not self._endpoint_url or not self._headers:
            self.connect()

        return self._post_with_auth_refresh(
            self._transport,
            JsonRequestSpec(
                provider=self._settings.provider,
                model=self._settings.model,
                url=self._endpoint_url,
                headers=self._headers,
                body=self._build_request_body(
                    instructions=instructions,
                    simple_prompt=simple_prompt,
                ),
                request_config=self._settings.redacted(),
                wait_input=wait_input,
                timeout=_REQUEST_TIMEOUT_SECS,
                error_policy=JsonErrorPolicy(
                    api_error_label="Google GCP OpenAI Responses API error",
                    rate_limit_exhausted_label=(
                        "Google GCP OpenAI Responses rate limit exceeded"
                    ),
                    overload_exhausted_label=(
                        "Google GCP OpenAI Responses API overloaded"
                    ),
                    request_failed_label="Google GCP OpenAI Responses request failed",
                    normalize_http_error=parse_json_error_body,
                    format_error=json_error_message,
                ),
                sleep=time.sleep,
            ),
            display=display,
            tracer=tracer,
            parse_response=self._parse_response,
            semantic_validator=_validate_google_gcp_openai_responses_response,
        )

    def _build_request_body(
        self,
        *,
        instructions: str | None,
        simple_prompt: str | None = None,
    ) -> dict[str, Any]:
        request_input: str | list[dict[str, Any]]
        if simple_prompt is not None:
            request_input = simple_prompt
        else:
            request_input = [
                _clone_json_dict(item) for item in self._input_history_items
            ]

        body: dict[str, Any] = {
            "model": self._settings.model,
            "input": request_input,
            "max_output_tokens": self._settings.max_tokens,
            "stream": False,
            "store": False,
        }
        if instructions:
            body["instructions"] = instructions
        if self._tools:
            body["tools"] = [_clone_json_dict(tool) for tool in self._tools]
            body["parallel_tool_calls"] = True
        return body

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        output_items = response_json.get("output", [])
        if not isinstance(output_items, list):
            output_items = []

        assistant_messages: list[str] = []
        reasoning_summary_parts: list[str] = []
        reasoning_content_parts: list[str] = []
        encrypted_reasoning_parts: list[str] = []
        function_calls: list[ToolCall] = []
        display_items: list[dict[str, Any]] = []
        history_output_items: list[dict[str, Any]] = []
        message_history_indexes: list[int] = []

        for item in output_items:
            if not isinstance(item, dict):
                continue
            history_item = response_history_item_for_input(item)
            history_output_items.append(history_item)
            item_type = item.get("type")
            if item_type == "reasoning":
                reasoning_summary_parts.extend(
                    _openai_responses_reasoning_summary_texts(item.get("summary"))
                )
                reasoning_content_parts.extend(
                    _openai_responses_reasoning_content_texts(item.get("content"))
                )
                encrypted_content = item.get("encrypted_content")
                if isinstance(encrypted_content, str) and encrypted_content:
                    encrypted_reasoning_parts.append(encrypted_content)
            elif item_type == "message":
                message_text = _openai_responses_message_text(item)
                if message_text:
                    assistant_messages.append(message_text)
                    message_history_indexes.append(len(history_output_items) - 1)
                    display_items.append({"type": "message", "text": message_text})
            elif item_type == "function_call":
                function_calls.append(_openai_responses_function_call(item))

        text = assistant_messages[-1] if assistant_messages else ""
        if len(message_history_indexes) > 1:
            skipped_message_indexes = set(message_history_indexes[:-1])
            history_output_items = [
                item
                for index, item in enumerate(history_output_items)
                if index not in skipped_message_indexes
            ]
        if not text:
            output_text = response_json.get("output_text")
            if isinstance(output_text, str):
                text = output_text.strip()
                if text:
                    display_items.append({"type": "message", "text": text})

        usage_obj = response_json.get("usage", {})
        input_tokens = _openai_responses_usage_value(usage_obj, "input_tokens")
        output_tokens = _openai_responses_usage_value(usage_obj, "output_tokens")
        total_tokens = _openai_responses_usage_value(usage_obj, "total_tokens")
        input_details = (
            usage_obj.get("input_tokens_details", {})
            if isinstance(usage_obj, dict)
            else {}
        )
        output_details = (
            usage_obj.get("output_tokens_details", {})
            if isinstance(usage_obj, dict)
            else {}
        )
        cached_input_tokens = _openai_responses_usage_value(
            input_details,
            "cached_tokens",
        )
        reasoning_tokens = _openai_responses_usage_value(
            output_details,
            "reasoning_tokens",
        )

        response_id = response_json.get("id")
        return CompletedResponse(
            response_id=response_id if isinstance(response_id, str) else None,
            text=text,
            usage=TokenUsage(
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                provider_total_tokens=total_tokens,
                context_tokens=total_tokens or (input_tokens + output_tokens),
                model=_openai_responses_model_name(response_json),
            ),
            function_calls=function_calls,
            reasoning_summary="\n\n".join(
                part for part in reasoning_summary_parts if part.strip()
            ).strip(),
            reasoning_content="\n\n".join(
                part for part in reasoning_content_parts if part.strip()
            ).strip(),
            provider_data={
                "display_items": display_items,
                "encrypted_reasoning_content": encrypted_reasoning_parts,
                "history_output_items": history_output_items,
                "reasoning": response_json.get("reasoning"),
            },
        )

    def _record_response(self, response: CompletedResponse) -> None:
        provider_data = response.provider_data
        if not isinstance(provider_data, dict):
            return
        output_items = provider_data.get("history_output_items")
        if not isinstance(output_items, list):
            return
        self._input_history_items.extend(
            _clone_json_dict(item) for item in output_items if isinstance(item, dict)
        )


class _AnthropicMessagesShape(_GoogleGcpShapeStub):
    shape_name: ClassVar[GoogleGcpShapeName] = "anthropic_messages"

    def __init__(
        self,
        *,
        settings: Settings,
        instructions: str,
        access_token_resolver: Callable[[], str] | None,
        tool_catalog: ToolCatalog,
        excluded_tools: set[str],
    ) -> None:
        super().__init__(
            settings=settings,
            instructions=instructions,
            access_token_resolver=access_token_resolver,
            tool_catalog=tool_catalog,
            excluded_tools=excluded_tools,
        )
        self._transport = JsonModelTransport()
        self._tools: list[dict[str, Any]] = []
        self._messages: list[dict[str, Any]] = []
        self._endpoint_url = google_gcp_endpoint_url(
            self._settings,
            _endpoint_shape(self.shape_name),
            model=_google_gcp_anthropic_endpoint_model(self._settings.model),
            require_project=False,
        )
        self.refresh_tools()

    def connect(self) -> None:
        auth = google_gcp_auth(
            self._settings,
            access_token_resolver=self._access_token_resolver,
            allow_api_key=self._supports_api_key_auth(),
        )
        self._auth = auth
        self._endpoint_url = self._endpoint_url_for_auth(
            auth,
            require_project=True,
        )
        headers = json_model_headers()
        headers.update(auth.headers)
        self._headers = headers

    def reset_conversation(self) -> None:
        super().reset_conversation()
        self._messages.clear()

    def set_previous_response_id(self, response_id: str | None) -> None:
        del response_id
        self._previous_response_id = None

    def get_conversation_checkpoint(self) -> str | None:
        return None

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        super().restore_messages(messages)
        self._messages = [
            _anthropic_message_record_to_message(message)
            for message in messages
            if _anthropic_message_record_can_restore(message)
        ]

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        super().restore_history_items(items)
        self._messages = [
            restored
            for item in items
            if (restored := _anthropic_history_item_to_message(item)) is not None
        ]

    def set_excluded_tools(self, excluded_tools: set[str]) -> None:
        self._excluded_tools = default_excluded_tool_names(excluded_tools)
        self.refresh_tools()

    def set_runtime_settings(self, settings: Settings) -> None:
        super().set_runtime_settings(settings)
        self.refresh_tools()

    def refresh_tools(self) -> None:
        excluded_tools = effective_excluded_tool_names(
            self._settings, self._excluded_tools
        )
        self._tools = self._tool_catalog.get_anthropic_tool_definitions(
            excluded_names=excluded_tools
        )

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
        input_value = self._accept_turn(
            user_message=user_message,
            user_input=user_input,
            tool_result_items=tool_result_items,
        )
        result = self._http_request(
            input_value=input_value,
            system_prompt=instructions or self._instructions,
            display=display,
            tracer=tracer,
        )
        record_response_usage(
            result,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
        )
        self._record_response(result)
        render_messages_response(display, result)
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
        if not response.function_calls:
            return [], False

        return execute_provider_tool_calls(
            response.function_calls,
            max_workers=max_workers,
            settings=self._settings,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            tool_catalog=self._tool_catalog,
            excluded_tools=self._excluded_tools,
            serialize_result=_anthropic_tool_result_item,
            sub_agent_depth=sub_agent_depth,
            parent_context=parent_context,
            tracer=tracer,
            tool_availability_overridden=self._tool_availability_overridden,
            workspace_root=getattr(self, "_workspace_root", None),
            workspace_directory_key=getattr(self, "_workspace_directory_key", None),
            execute_calls=_execute_tool_calls,
        )

    def _accept_turn(
        self,
        *,
        user_message: str | None,
        user_input: UserTurnInput | None,
        tool_result_items: list[dict[str, Any]] | None,
    ) -> str | list[dict[str, Any]]:
        if user_input is None and user_message is not None:
            user_input = UserTurnInput(text=user_message)

        if user_input is not None:
            self._messages.append(
                {
                    "role": "user",
                    "content": _anthropic_user_content_blocks(user_input),
                }
            )
            return user_input.text

        if tool_result_items is not None:
            self._messages.append(
                {
                    "role": "user",
                    "content": [_clone_json_dict(item) for item in tool_result_items],
                }
            )
            return tool_result_items

        raise ValueError("Either user_input or tool_result_items is required")

    def _http_request(
        self,
        *,
        input_value: str | list[dict[str, Any]],
        system_prompt: str | None,
        display: DisplayProtocol,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        if not self._endpoint_url or not self._headers:
            self.connect()

        return self._post_with_auth_refresh(
            self._transport,
            JsonRequestSpec(
                provider=self._settings.provider,
                model=self._settings.model,
                url=self._endpoint_url,
                headers=self._headers,
                body=self._build_request_body(system_prompt=system_prompt),
                request_config=self._settings.redacted(),
                wait_input=input_value,
                timeout=_REQUEST_TIMEOUT_SECS,
                error_policy=JsonErrorPolicy(
                    api_error_label="Google GCP Anthropic Messages API error",
                    rate_limit_exhausted_label=(
                        "Google GCP Anthropic Messages rate limit exceeded"
                    ),
                    overload_exhausted_label=(
                        "Google GCP Anthropic Messages API overloaded"
                    ),
                    request_failed_label=(
                        "Google GCP Anthropic Messages request failed"
                    ),
                    normalize_http_error=normalize_anthropic_http_error,
                    format_error=json_error_message,
                ),
                sleep=time.sleep,
            ),
            display=display,
            tracer=tracer,
            parse_response=self._parse_response,
        )

    def _build_request_body(self, *, system_prompt: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "anthropic_version": _VERTEX_ANTHROPIC_VERSION,
            "max_tokens": self._settings.max_tokens,
            "stream": False,
            "messages": [_clone_json_dict(message) for message in self._messages],
        }
        if self._tools:
            body["tools"] = [_clone_json_dict(tool) for tool in self._tools]
        if system_prompt:
            body["system"] = system_prompt
        return body

    def _endpoint_url_for_settings(self, *, require_project: bool) -> str:
        return google_gcp_endpoint_url(
            self._settings,
            _endpoint_shape(self.shape_name),
            model=_google_gcp_anthropic_endpoint_model(self._settings.model),
            require_project=require_project,
        )

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        content_blocks = _anthropic_content_blocks(response_json.get("content"))

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        has_redacted_thinking = False
        function_calls: list[ToolCall] = []
        web_search_sources: list[WebSearchSource] = []
        display_items: list[dict[str, Any]] = []
        pending_web_search_queries: dict[str, list[str]] = {}

        for block in content_blocks:
            block_type = block.get("type")

            if block_type == "thinking":
                thinking_text = block.get("thinking", "")
                if isinstance(thinking_text, str) and thinking_text:
                    thinking_parts.append(thinking_text)

            elif block_type == "redacted_thinking":
                has_redacted_thinking = True

            elif block_type == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text:
                    text_parts.append(text)
                    display_items.append({"type": "text", "text": text})

            elif block_type == "tool_use":
                name = block.get("name", "")
                function_calls.append(
                    ToolCall(
                        call_id=str(block.get("id", "")),
                        name=name if isinstance(name, str) else "",
                        arguments=block.get("input"),
                    )
                )

            elif block_type == "server_tool_use":
                if str(block.get("name", "")).startswith("web_search"):
                    pending_web_search_queries[str(block.get("id", ""))] = (
                        _extract_anthropic_web_search_queries(block)
                    )

            elif block_type == "web_search_tool_result":
                sources_for_block: list[dict[str, str]] = []
                for entry in block.get("content", []):
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("type") != "web_search_result":
                        continue
                    source = WebSearchSource(
                        title=str(entry.get("title", "")),
                        url=str(entry.get("url", "")),
                        snippet=str(entry.get("page_snippet", "")),
                    )
                    web_search_sources.append(source)
                    sources_for_block.append(
                        {
                            "title": source.title,
                            "url": source.url,
                            "snippet": source.snippet,
                        }
                    )
                display_items.append(
                    {
                        "type": "web_search",
                        "queries": pending_web_search_queries.get(
                            str(block.get("tool_use_id", "")),
                            [],
                        ),
                        "sources": sources_for_block,
                    }
                )

        usage_obj = response_json.get("usage", {})
        base_input_tokens = _usage_int(usage_obj, "input_tokens")
        output_tokens = _usage_int(usage_obj, "output_tokens")
        cache_read_tokens = _usage_int(usage_obj, "cache_read_input_tokens")
        cache_creation_tokens = _usage_int(usage_obj, "cache_creation_input_tokens")

        cache_creation_obj = (
            usage_obj.get("cache_creation", {}) if isinstance(usage_obj, dict) else {}
        )
        cache_1h = _usage_int(cache_creation_obj, "ephemeral_1h_input_tokens")
        cache_5m = max(cache_creation_tokens - cache_1h, 0)
        total_input = base_input_tokens + cache_read_tokens + cache_creation_tokens

        return CompletedResponse(
            response_id=_string_or_none(response_json.get("id")),
            text="\n\n".join(text_parts).strip(),
            usage=TokenUsage(
                input_tokens=total_input,
                cached_input_tokens=cache_read_tokens,
                cache_write_tokens=cache_5m,
                cache_write_1h_tokens=cache_1h,
                output_tokens=output_tokens,
                context_tokens=total_input + output_tokens,
                model=_string_or_empty(response_json.get("model")),
            ),
            function_calls=function_calls,
            provider_data={
                "content_blocks": content_blocks,
                "thinking_parts": thinking_parts,
                "has_redacted_thinking": has_redacted_thinking,
                "display_items": display_items,
            },
            web_search_sources=web_search_sources,
        )

    def _record_response(self, response: CompletedResponse) -> None:
        provider_data = response.provider_data
        if not isinstance(provider_data, dict):
            return
        content_blocks = provider_data.get("content_blocks")
        if not isinstance(content_blocks, list):
            return
        self._messages.append(
            {
                "role": "assistant",
                "content": [
                    _clone_json_dict(block)
                    for block in content_blocks
                    if isinstance(block, dict)
                ],
            }
        )


_SHAPE_TYPES: dict[GoogleGcpShapeName, type[_GoogleGcpShapeStub]] = {
    "gemini_generate_content": _GeminiGenerateContentShape,
    "openai_chat_completions": _OpenAIChatCompletionsShape,
    "openai_responses": _OpenAIResponsesShape,
    "anthropic_messages": _AnthropicMessagesShape,
}


def google_gcp_shape_for_model(
    model: str,
    *,
    env: Mapping[str, str] | None = None,
) -> GoogleGcpShapeName:
    """Return the Google Cloud provider shape for a model name."""
    source = os.environ if env is None else env
    override = source.get(GOOGLE_GCP_SHAPE_ENV, "").strip().lower()
    if override:
        if override not in GOOGLE_GCP_SHAPES:
            allowed = ", ".join(GOOGLE_GCP_SHAPES)
            raise ValueError(f"{GOOGLE_GCP_SHAPE_ENV} must be one of: {allowed}.")
        return cast(GoogleGcpShapeName, override)

    normalized = model.strip().lower()
    if "grok" in normalized or normalized.startswith("xai/"):
        return "openai_responses"
    if normalized.startswith("claude") or "/claude" in normalized:
        return "anthropic_messages"
    if normalized.startswith("anthropic/"):
        return "anthropic_messages"
    if normalized.startswith("gemini") or "/gemini" in normalized:
        return "gemini_generate_content"
    if normalized.startswith("google/"):
        return "gemini_generate_content"
    if "/" in normalized:
        return "openai_chat_completions"
    return "gemini_generate_content"


def _create_google_gcp_shape(
    shape_name: GoogleGcpShapeName,
    *,
    settings: Settings,
    instructions: str,
    access_token_resolver: Callable[[], str] | None,
    tool_catalog: ToolCatalog,
    excluded_tools: set[str],
) -> _GoogleGcpShapeStub:
    return _SHAPE_TYPES[shape_name](
        settings=settings,
        instructions=instructions,
        access_token_resolver=access_token_resolver,
        tool_catalog=tool_catalog,
        excluded_tools=excluded_tools,
    )


def _endpoint_shape(shape_name: GoogleGcpShapeName) -> GoogleGcpEndpointShape:
    return cast(GoogleGcpEndpointShape, shape_name)


def _google_gcp_anthropic_endpoint_model(model: str) -> str:
    normalized = model.strip()
    if normalized.lower().startswith("anthropic/"):
        return normalized.split("/", 1)[1]
    return normalized


def _google_gcp_openai_responses_tools(
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return Responses tools compatible with Google Cloud Grok validation."""
    sanitized_tools: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        sanitized_tool = _clone_json_dict(tool)
        sanitized_tool["parameters"] = _google_gcp_json_schema_for_tool(
            sanitized_tool.get("parameters")
        )
        sanitized_tools.append(sanitized_tool)
    return sanitized_tools


def _google_gcp_json_schema_for_tool(schema: Any) -> dict[str, Any]:
    sanitized = _google_gcp_sanitize_json_schema(schema)
    return sanitized if isinstance(sanitized, dict) else {}


def _google_gcp_sanitize_json_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_google_gcp_sanitize_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    sanitized: dict[str, Any] = {}
    union_option_labels: list[str] = []
    for key, raw_child in value.items():
        if key in {"oneOf", "anyOf"}:
            union_option_labels.extend(_json_schema_option_labels(raw_child))
            continue
        if key in {"allOf", "not", "if", "then", "else"}:
            continue
        sanitized[key] = _google_gcp_sanitize_json_schema(raw_child)

    if union_option_labels:
        description = str(sanitized.get("description") or "").strip()
        options = ", ".join(dict.fromkeys(union_option_labels))
        suffix = f"Accepted value shapes: {options}."
        sanitized["description"] = f"{description} {suffix}".strip()

    return sanitized


def _json_schema_option_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for option in value:
        if not isinstance(option, dict):
            continue
        label = _json_schema_option_label(option)
        if label:
            labels.append(label)
    return labels


def _json_schema_option_label(option: dict[str, Any]) -> str:
    option_type = option.get("type")
    if option_type == "array":
        item_schema = option.get("items", {})
        item_type = item_schema.get("type") if isinstance(item_schema, dict) else None
        if isinstance(item_type, str):
            return f"array of {item_type}"
    if isinstance(option_type, str):
        return option_type
    return ""


def _is_google_gcp_token_expiry_error(message: str) -> bool:
    normalized = message.lower()
    return (
        "access_token_expired" in normalized
        or "token expired" in normalized
        or "access token expired" in normalized
        or ("unauthenticated" in normalized and "expired" in normalized)
    )


def _is_google_gcp_api_key_auth_unsupported_error(message: str) -> bool:
    normalized = message.lower()
    return (
        "access_token_type_unsupported" in normalized
        or "api_key_service_blocked" in normalized
        or "api keys are not supported by this api" in normalized
        or "expected oauth 2 access token" in normalized
        or "expected oauth2 access token" in normalized
    )


def _validate_google_gcp_openai_responses_response(
    response_json: dict[str, Any],
) -> None:
    """Raise for Grok Responses model errors returned as HTTP 200 payloads."""
    error = response_json.get("error")
    if error in (None, "") and (
        "code" not in response_json or "output" in response_json
    ):
        return

    message = _google_gcp_openai_responses_error_message(response_json)
    from pbi_agent.providers.transport import SemanticResponseError

    raise SemanticResponseError(message, response_json)


def _google_gcp_openai_responses_error_message(
    response_json: dict[str, Any],
) -> str:
    error = response_json.get("error")
    code = response_json.get("code")
    if isinstance(error, dict):
        raw_message = error.get("message") or error.get("error") or error.get("status")
        message = str(raw_message or "Model returned an error response.")
        raw_code = error.get("code") or error.get("status") or code
    elif isinstance(error, str) and error:
        message = error
        raw_code = code
    else:
        message = "Model returned an error response."
        raw_code = code

    if raw_code not in (None, ""):
        code_text = str(raw_code)
        if code_text not in message:
            message = f"{message} ({code_text})"
    return f"Google GCP OpenAI Responses API error 200: {message}"


def _anthropic_user_content_blocks(user_input: UserTurnInput) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for image in user_input.images:
        blocks.append(_anthropic_image_block(image))
    if user_input.text:
        blocks.append({"type": "text", "text": user_input.text})
    return blocks or [{"type": "text", "text": ""}]


def _anthropic_message_record_can_restore(message: MessageRecord) -> bool:
    if message.role not in {"user", "assistant"}:
        return False
    return bool(message.content or message.image_attachments)


def _anthropic_message_record_to_message(message: MessageRecord) -> dict[str, Any]:
    if message.role == "user" and message.image_attachments:
        return {
            "role": message.role,
            "content": _anthropic_user_content_blocks(
                UserTurnInput(
                    text=message.content,
                    images=[
                        load_uploaded_image(attachment.upload_id)
                        for attachment in message.image_attachments
                    ],
                )
            ),
        }
    return {
        "role": message.role,
        "content": [{"type": "text", "text": message.content}],
    }


def _anthropic_history_item_to_message(item: dict[str, Any]) -> dict[str, Any] | None:
    item_type = item.get("type")
    if item_type == "message":
        message = item.get("message")
        if isinstance(message, MessageRecord) and _anthropic_message_record_can_restore(
            message
        ):
            return _anthropic_message_record_to_message(message)
        return None
    if item_type == "tool_call":
        call_id = str(item.get("call_id") or "")
        name = str(item.get("name") or "")
        if not call_id or not name:
            return None
        return {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": item.get("arguments") or {},
                }
            ],
        }
    if item_type == "tool_call_group":
        tool_use_blocks: list[dict[str, Any]] = []
        for call in item.get("calls", []):
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("call_id") or "")
            name = str(call.get("name") or "")
            if not call_id or not name:
                continue
            tool_use_blocks.append(
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": call.get("arguments") or {},
                }
            )
        if not tool_use_blocks:
            return None
        return {"role": "assistant", "content": tool_use_blocks}
    if item_type == "tool_result":
        call_id = str(item.get("call_id") or "")
        if not call_id:
            return None
        output = item.get("output")
        result_block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": output if isinstance(output, str) else json.dumps(output),
        }
        if item.get("is_error"):
            result_block["is_error"] = True
        return {"role": "user", "content": [result_block]}
    if item_type == "tool_result_group":
        result_blocks: list[dict[str, Any]] = []
        for result_item in item.get("results", []):
            if not isinstance(result_item, dict):
                continue
            call_id = str(result_item.get("call_id") or "")
            if not call_id:
                continue
            output = result_item.get("output")
            grouped_result_block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": output if isinstance(output, str) else json.dumps(output),
            }
            if result_item.get("is_error"):
                grouped_result_block["is_error"] = True
            result_blocks.append(grouped_result_block)
        if not result_blocks:
            return None
        return {"role": "user", "content": result_blocks}
    return None


def _anthropic_tool_result_content(result: ToolResult) -> str | list[dict[str, Any]]:
    if not result.attachments:
        return result.output_json

    blocks = [_anthropic_image_block(image) for image in result.attachments]
    blocks.append({"type": "text", "text": result.output_json})
    return blocks


def _anthropic_tool_result_item(result: ToolResult) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": result.call_id,
        "content": _anthropic_tool_result_content(result),
        **({"is_error": True} if result.is_error else {}),
    }


def _anthropic_image_block(image: ImageAttachment) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": image.mime_type,
            "data": image.data_base64,
        },
    }


def _anthropic_content_blocks(raw_content: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_content, list):
        return []
    return [_clone_json_dict(block) for block in raw_content if isinstance(block, dict)]


def _extract_anthropic_web_search_queries(block: dict[str, Any]) -> list[str]:
    raw_input = block.get("input")
    if not isinstance(raw_input, dict):
        return []
    raw_query = raw_input.get("query")
    if isinstance(raw_query, str) and raw_query.strip():
        return [raw_query.strip()]
    return []


def _usage_int(raw_obj: Any, key: str) -> int:
    if not isinstance(raw_obj, dict):
        return 0
    try:
        return int(raw_obj.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _string_or_empty(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _openai_responses_user_input_item(prompt: str) -> dict[str, Any]:
    return {"role": "user", "content": prompt}


def _openai_responses_history_items_to_input_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    restored_items: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") == "tool_call_group":
            child_items = item.get("calls", [])
        elif item.get("type") == "tool_result_group":
            child_items = item.get("results", [])
        else:
            child_items = None

        if child_items is not None:
            if not isinstance(child_items, list):
                continue
            for child in child_items:
                if (
                    isinstance(child, dict)
                    and (
                        restored := _openai_responses_history_item_to_input_item(child)
                    )
                    is not None
                ):
                    restored_items.append(restored)
            continue

        if (restored := _openai_responses_history_item_to_input_item(item)) is not None:
            restored_items.append(restored)
    return restored_items


def _openai_responses_history_item_to_input_item(
    item: dict[str, Any],
) -> dict[str, Any] | None:
    item_type = item.get("type")
    if item_type == "provider_input_item":
        raw_item = item.get("item")
        if item.get("format") == "openai_responses" and isinstance(raw_item, dict):
            return response_history_item_for_input(raw_item)
        return None
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
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": (
                arguments if isinstance(arguments, str) else json.dumps(arguments or {})
            ),
        }
    if item_type == "tool_result":
        call_id = str(item.get("call_id") or "")
        if not call_id:
            return None
        output = item.get("output")
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output if isinstance(output, str) else json.dumps(output),
        }
    return None


def _openai_responses_reasoning_summary_texts(raw_summary: Any) -> list[str]:
    if isinstance(raw_summary, str):
        return [raw_summary] if raw_summary else []
    if not isinstance(raw_summary, list):
        return []

    summary_parts: list[str] = []
    for entry in raw_summary:
        if isinstance(entry, dict):
            if entry.get("type") == "summary_text":
                text = entry.get("text", "")
                if isinstance(text, str) and text:
                    summary_parts.append(text)
        elif isinstance(entry, str) and entry:
            summary_parts.append(entry)
    return summary_parts


def _openai_responses_reasoning_content_texts(raw_content: Any) -> list[str]:
    if isinstance(raw_content, str):
        return [raw_content] if raw_content else []
    if not isinstance(raw_content, list):
        return []

    content_parts: list[str] = []
    for entry in raw_content:
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        if entry_type in {"reasoning_text", "text"}:
            text = entry.get("text", "")
            if isinstance(text, str) and text:
                content_parts.append(text)
    return content_parts


def _openai_responses_message_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") in {"output_text", "text"}:
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return "".join(text_parts).strip()


def _openai_responses_function_call(item: dict[str, Any]) -> ToolCall:
    raw_args = item.get("arguments", "")
    arguments: dict[str, Any] | str | None
    if isinstance(raw_args, str):
        try:
            arguments = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            arguments = raw_args
    else:
        arguments = raw_args

    call_id = item.get("call_id") or item.get("id") or ""
    return ToolCall(
        call_id=str(call_id),
        name=str(item.get("name", "")),
        arguments=arguments,
    )


def _openai_responses_usage_value(raw_obj: Any, key: str) -> int:
    if not isinstance(raw_obj, dict):
        return 0
    try:
        return int(raw_obj.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _openai_responses_model_name(response_json: dict[str, Any]) -> str:
    model = response_json.get("model")
    return model if isinstance(model, str) else ""


def _clone_json_dict(item: dict[str, Any]) -> dict[str, Any]:
    cloned = json.loads(json.dumps(item))
    return cloned if isinstance(cloned, dict) else dict(item)


def _raise_shape_not_implemented(shape_name: GoogleGcpShapeName) -> NoReturn:
    raise NotImplementedError(
        "Google GCP provider shape "
        f"{shape_name!r} is not implemented yet. "
        "Add a dedicated Google GCP shape implementation before routing models "
        "to it."
    )


__all__ = [
    "GOOGLE_GCP_SHAPE_ENV",
    "GOOGLE_GCP_SHAPES",
    "GoogleGcpProvider",
    "GoogleGcpShapeName",
    "google_gcp_shape_for_model",
]
