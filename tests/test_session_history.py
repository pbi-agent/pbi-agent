from __future__ import annotations

from contextlib import contextmanager
import io
import json
import urllib.error
import urllib.request

import pytest

from pbi_agent.agent import session as session_module
from pbi_agent.agent.session.commands import user_turn_history_text
from pbi_agent.agent.session.history import _new_input_delta
from pbi_agent.auth.models import OAuthSessionAuth
from pbi_agent.auth.providers.github_copilot import GITHUB_COPILOT_RESPONSES_URL
from pbi_agent.auth.providers.openai_chatgpt import OPENAI_CHATGPT_RESPONSES_URL
from pbi_agent.config import Settings
from pbi_agent.display.protocol import QueuedInput
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    ToolCall,
    UserTurnInput,
)
from pbi_agent.observability import RunTracer
from pbi_agent.providers.chatgpt_codex_transport import ChatGPTCodexWebSocketError
from pbi_agent.providers.github_copilot_provider import GitHubCopilotProvider
from pbi_agent.providers.google_provider import GoogleProvider
from pbi_agent.providers.openai_provider import OpenAIProvider
from pbi_agent.session_store import SessionStore


def _record_tool_turn(
    store,
    session_id,
    prompt,
    *,
    status="completed",
    checkpoints=(),
    tool_output="tool result",
    provider="openai",
    final_answer=True,
    history_prompt=None,
    request_input=None,
    persist_before_run=False,
):
    message_text = prompt if history_prompt is None else history_prompt
    if persist_before_run:
        store.add_message(session_id, "user", message_text)
    run_id = store.create_run_session(
        session_id=session_id,
        agent_name="main",
        agent_type="session_turn",
        provider=provider,
        provider_id=None,
        profile_id=None,
        model="test-model",
        status=status,
    )
    if not persist_before_run:
        store.add_message(session_id, "user", message_text)
    store.add_observability_event(
        run_session_id=run_id,
        session_id=session_id,
        step_index=0,
        event_type="model_call",
        request_payload={
            "input": (
                [{"role": "user", "content": prompt}]
                if request_input is None
                else request_input
            )
        },
        response_payload={
            "output": [
                {
                    "type": "function_call",
                    "call_id": run_id,
                    "name": "shell",
                    "arguments": '{"command":"pwd"}',
                },
            ]
        },
        success=True,
    )
    store.add_observability_event(
        run_session_id=run_id,
        session_id=session_id,
        step_index=1,
        event_type="tool_call",
        tool_call_id=run_id,
        tool_name="shell",
        tool_input={"command": "pwd"},
        tool_output=tool_output,
        success=True,
    )
    next_input = [
        {"type": "function_call_output", "call_id": run_id, "output": tool_output}
    ]
    if checkpoints:
        for checkpoint in checkpoints:
            store.add_message(session_id, "user", checkpoint)
        next_input.append({"role": "user", "content": "\n\n".join(checkpoints)})
    store.add_observability_event(
        run_session_id=run_id,
        session_id=session_id,
        step_index=2,
        event_type="model_call",
        request_payload={"input": next_input},
        response_payload=(
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": f"Answer: {prompt}"}
                        ],
                    }
                ]
            }
            if final_answer
            else {"error": {"message": "Invalid previous_response_id"}}
        ),
        success=final_answer,
        status_code=200 if final_answer else 400,
    )
    if final_answer:
        store.add_message(session_id, "assistant", f"Answer: {prompt}")
    return run_id


def _next_request_input(provider, monkeypatch, display_spy):
    requests = []

    def urlopen(request, timeout):
        del timeout
        requests.append(json.loads(request.data))
        return io.BytesIO(b'{"id":"next-response","output":[],"outputs":[]}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    provider.request_turn(
        user_message="continue",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )
    assert "previous_response_id" not in requests[0]
    assert "previous_interaction_id" not in requests[0]
    return requests[0]["input"]


def _restore_history(provider, store, session_id, display, restore, include_tools):
    if restore == "resume":
        session_module._resume_session(
            provider=provider,
            store=store,
            session_id=session_id,
            session_usage=TokenUsage(),
            display=display,
            replay_history=False,
            include_tool_history=include_tools,
        )
    else:
        session_module.refresh_provider_history_from_store(
            provider,
            store,
            session_id,
            reason="turn",
            include_tool_history=include_tools,
        )


def _record_failed_provider_turn(
    store, session_id, provider, user_input, monkeypatch, display
):
    requests = []
    google = provider.settings.provider == "google"
    call = {
        "type": "function_call",
        "id" if google else "call_id": "recovery-tool",
        "name": "shell",
        "arguments": {"command": "pwd"} if google else '{"command":"pwd"}',
    }
    result = {
        "type": "function_result" if google else "function_call_output",
        "call_id": "recovery-tool",
        "name": "shell",
        "result" if google else "output": "recovered result",
    }

    def urlopen(request, timeout):
        del timeout
        requests.append(json.loads(request.data))
        if len(requests) == 1:
            return io.BytesIO(
                json.dumps(
                    {"id": "tool-response", "outputs" if google else "output": [call]}
                ).encode()
            )
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"error":{"message":"Invalid previous response"}}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    tracer = RunTracer.start(
        store=store,
        session_id=session_id,
        agent_name="main",
        agent_type="session_turn",
        provider=provider.settings.provider,
        provider_id=None,
        profile_id=None,
        model=provider.settings.model,
    )
    store.add_message(session_id, "user", user_turn_history_text(user_input))
    provider.request_turn(
        user_input=user_input,
        display=display,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
        tracer=tracer,
    )
    tracer.log_tool_call(
        tool_name="shell",
        tool_call_id="recovery-tool",
        tool_input={"command": "pwd"},
        tool_output="recovered result",
        duration_ms=1,
        success=True,
    )
    with pytest.raises(RuntimeError, match="400"):
        provider.request_turn(
            tool_result_items=[result],
            display=display,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
            tracer=tracer,
        )
    tracer.finish(status="failed", usage=TokenUsage())
    return requests


@pytest.mark.parametrize("request_metadata", [False, True])
@pytest.mark.parametrize("existing_metadata", [False, True])
@pytest.mark.parametrize("prior_history", [False, True])
def test_response_input_delta_compares_normalized_items_without_mutation(
    request_metadata, existing_metadata, prior_history
):
    prompt = {"role": "user", "content": "check workspace"}
    call = {
        "type": "function_call",
        "call_id": "tool-1",
        "name": "shell",
        "arguments": '{"command":"pwd"}',
    }
    metadata = {"id": "output-1", "status": "completed"}
    previous_items = (
        [{"role": "assistant", "content": "earlier"}] if prior_history else []
    )
    delta_item = {
        "type": "function_call_output",
        "call_id": "tool-1",
        "output": [{"type": "input_text", "text": "workspace"}],
        "id": "result-1",
    }
    request_items = [
        *previous_items,
        prompt,
        {**call, **(metadata if request_metadata else {})},
        delta_item,
    ]
    existing_items = [prompt, {**call, **(metadata if existing_metadata else {})}]
    original = json.dumps([request_items, existing_items])

    delta = _new_input_delta(request_items, existing_items)

    assert delta == [delta_item]
    assert delta[0] is not delta_item
    assert delta[0]["output"] is not delta_item["output"]
    assert json.dumps([request_items, existing_items]) == original
    # Only output metadata is ignorable; a changed call is still new input.
    existing_items[-1]["arguments"] = '{"command":"ls"}'
    assert _new_input_delta(request_items, existing_items) == request_items


@pytest.mark.parametrize("restore", ["resume", "refresh"])
@pytest.mark.parametrize("include_tool_history", [False, True])
@pytest.mark.parametrize("retry_succeeds", [False, True])
@pytest.mark.parametrize("tool_kind", ["function", "custom_tool"])
def test_response_history_replays_http_retry_inputs_once(
    tmp_path,
    monkeypatch,
    display_spy,
    restore,
    include_tool_history,
    retry_succeeds,
    tool_kind,
):
    settings = Settings(api_key="test", provider="openai", max_retries=2)
    provider = OpenAIProvider(settings)
    calls = [
        {
            "type": f"{tool_kind}_call",
            "call_id": f"retry-tool-{index}",
            "name": "shell" if tool_kind == "function" else "apply_patch",
            "arguments" if tool_kind == "function" else "input": (
                '{"command":"pwd"}'
                if tool_kind == "function"
                else "*** Begin Patch\n*** Add File: test.txt\n+test\n*** End Patch\n"
            ),
        }
        for index in range(2)
    ]
    results = [
        {
            "type": f"{tool_kind}_call_output",
            "call_id": call["call_id"],
            "output": "recovered result",
        }
        for call in calls
    ]
    requests = []

    def urlopen(request, timeout):
        del timeout
        requests.append(json.loads(request.data))
        if len(requests) == 2:
            payload = {"id": "tool-response", "output": calls}
        elif len(requests) == 5 and retry_succeeds:
            payload = {
                "id": "final-response",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Done after retry"}
                        ],
                    }
                ],
            }
        else:
            raise urllib.error.HTTPError(
                request.full_url,
                500,
                "Internal Server Error",
                {},
                io.BytesIO(b'{"error":{"message":"retry this request"}}'),
            )
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(
        "pbi_agent.providers.openai_provider.time.sleep", lambda _seconds: None
    )
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), "openai", "test-model")
        tracer = RunTracer.start(
            store=store,
            session_id=session_id,
            agent_name="main",
            agent_type="session_turn",
            provider="openai",
            provider_id=None,
            profile_id=None,
            model=settings.model,
        )
        store.add_message(session_id, "user", "retry task")
        provider.request_turn(
            user_message="retry task",
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
            tracer=tracer,
        )
        for call in calls:
            tracer.log_tool_call(
                tool_name=call["name"],
                tool_call_id=call["call_id"],
                tool_input=call.get("arguments", call.get("input")),
                tool_output="recovered result",
                duration_ms=1,
                success=True,
            )
        store.add_message(session_id, "user", "also check tests")

        def follow_up():
            return provider.request_turn(
                tool_result_items=results,
                steer_user_input=UserTurnInput(text="also check tests"),
                display=display_spy,
                session_usage=TokenUsage(),
                turn_usage=TokenUsage(),
                tracer=tracer,
            )

        if retry_succeeds:
            response = follow_up()
            store.add_message(session_id, "assistant", response.text)
        else:
            with pytest.raises(RuntimeError, match="500"):
                follow_up()
        tracer.finish(
            status="completed" if retry_succeeds else "failed", usage=TokenUsage()
        )
        assert len(requests) == 5
        assert requests[0] == requests[1]
        assert requests[2] == requests[3] == requests[4]
        events = store.list_observability_events(run_session_id=tracer.run_session_id)
        assert len([event for event in events if event.event_type == "model_call"]) == 5
        if restore == "resume":
            provider = OpenAIProvider(settings)
        _restore_history(
            provider, store, session_id, display_spy, restore, include_tool_history
        )

    items = _next_request_input(provider, monkeypatch, display_spy)
    expected_calls = calls if include_tool_history or not retry_succeeds else []
    assert [item for item in items if item.get("type") == f"{tool_kind}_call"] == (
        expected_calls
    )
    assert [
        item for item in items if item.get("type") == f"{tool_kind}_call_output"
    ] == (results if expected_calls else [])
    assert json.dumps(items).count("retry task") == 1
    assert json.dumps(items).count("also check tests") == 1
    assert json.dumps(items).count("Done after retry") == int(retry_succeeds)


@pytest.mark.parametrize("restore", ["resume", "refresh"])
@pytest.mark.parametrize("include_tool_history", [False, True])
@pytest.mark.parametrize("prior_history", [False, True])
@pytest.mark.parametrize(
    ("source_provider", "tool_kind"),
    [
        ("github_copilot", "function"),
        ("chatgpt", "function"),
        ("chatgpt", "custom_tool"),
    ],
)
def test_failed_stateless_responses_followup_restores_one_exchange(
    tmp_path,
    monkeypatch,
    display_spy,
    restore,
    include_tool_history,
    prior_history,
    source_provider,
    tool_kind,
):
    copilot = source_provider == "github_copilot"
    settings = Settings(
        provider=source_provider,
        model="gpt-5.4",
        max_retries=0,
        responses_url=(
            GITHUB_COPILOT_RESPONSES_URL if copilot else OPENAI_CHATGPT_RESPONSES_URL
        ),
        auth=OAuthSessionAuth(
            provider_id=source_provider,
            backend="github_copilot" if copilot else "openai_chatgpt",
            access_token="test-token",
            refresh_token=None,
        ),
    )
    provider_type = GitHubCopilotProvider if copilot else OpenAIProvider
    provider = provider_type(settings)
    call = {
        "type": f"{tool_kind}_call",
        "call_id": "recovery-tool",
        "name": "shell" if tool_kind == "function" else "apply_patch",
        "arguments" if tool_kind == "function" else "input": (
            '{"command":"pwd"}'
            if tool_kind == "function"
            else "*** Begin Patch\n*** Add File: test.txt\n+test\n*** End Patch\n"
        ),
    }
    replay_output = [
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "Check the workspace"}],
            "encrypted_content": "encrypted-reasoning",
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Checking now"}],
        },
        call,
    ]
    raw_output = [
        {**item, "id": f"output-{index}", "status": "completed"}
        for index, item in enumerate(replay_output)
    ]
    raw_output[1]["phase"] = "commentary"
    raw_output[1]["content"] = [
        {
            "type": "output_text",
            "text": "Checking now",
            "annotations": [],
            "logprobs": [],
        }
    ]
    result = {
        "type": f"{tool_kind}_call_output",
        "call_id": "recovery-tool",
        "output": "recovered result",
    }
    requests = []
    error_payload = {"error": {"message": "Invalid follow-up"}}

    def response_payload(request_body):
        requests.append(json.loads(json.dumps(request_body)))
        return {
            "id": f"response-{len(requests)}",
            "output": raw_output if len(requests) == 1 else [],
        }

    def urlopen(request, timeout):
        del timeout
        payload = response_payload(json.loads(request.data))
        if len(requests) == 2:
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {},
                io.BytesIO(json.dumps(error_payload).encode()),
            )
        return io.BytesIO(json.dumps(payload).encode())

    def send_websocket_request(self, *, request_body, **kwargs):
        del self, kwargs
        payload = response_payload(request_body)
        if len(requests) == 2:
            raise ChatGPTCodexWebSocketError(
                "Invalid follow-up", status=400, payload=error_payload
            )
        return [{"type": "response.completed", "response": payload}]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(
        "pbi_agent.providers.chatgpt_codex_backend._EnabledChatGPTCodexBackend.send_websocket_request",
        send_websocket_request,
    )
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path), source_provider, settings.model
        )
        previous_items = (
            [
                {"role": "user", "content": "previous task"},
                {"role": "assistant", "content": "previous answer"},
            ]
            if prior_history
            else []
        )
        for item in previous_items:
            store.add_message(session_id, item["role"], item["content"])
        provider.restore_messages(store.list_messages(session_id))
        tracer = RunTracer.start(
            store=store,
            session_id=session_id,
            agent_name="main",
            agent_type="session_turn",
            provider=source_provider,
            provider_id=None,
            profile_id=None,
            model=settings.model,
        )
        prompt = {"role": "user", "content": "recover this task"}
        store.add_message(session_id, "user", prompt["content"])
        provider.request_turn(
            user_message=prompt["content"],
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
            tracer=tracer,
        )
        tracer.log_tool_call(
            tool_name=call["name"],
            tool_call_id=call["call_id"],
            tool_input=call.get("arguments", call.get("input")),
            tool_output=result["output"],
            duration_ms=1,
            success=True,
        )
        # ChatGPT replays locally when the previous response is unavailable.
        # Copilot always uses local replay, even with a previous response ID.
        if not copilot:
            provider.set_previous_response_id(None)
        with pytest.raises(RuntimeError, match="Invalid follow-up"):
            provider.request_turn(
                tool_result_items=[result],
                display=display_spy,
                session_usage=TokenUsage(),
                turn_usage=TokenUsage(),
                tracer=tracer,
            )
        tracer.finish(status="failed", usage=TokenUsage())
        expected_history = [*previous_items, prompt, *replay_output, result]
        assert "previous_response_id" not in requests[1]
        assert requests[1]["input"] == expected_history
        if restore == "resume":
            provider = provider_type(settings)
        _restore_history(
            provider, store, session_id, display_spy, restore, include_tool_history
        )

    provider.request_turn(
        user_message="continue",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )
    assert len(requests) == 3
    assert "previous_response_id" not in requests[-1]
    assert requests[-1]["input"] == [
        *expected_history,
        {"role": "user", "content": "continue"},
    ]


@pytest.mark.parametrize("restore", ["resume", "refresh"])
@pytest.mark.parametrize("include_tool_history", [False, True])
def test_failed_google_step_input_turn_restores_tools(
    tmp_path, monkeypatch, display_spy, restore, include_tool_history
):
    settings = Settings(api_key="test", provider="google", max_retries=0)
    provider = GoogleProvider(settings)
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), "google", "test-model")
        store.add_message(session_id, "user", "previous task")
        store.add_message(session_id, "assistant", "previous answer")
        provider.restore_messages(store.list_messages(session_id))
        requests = _record_failed_provider_turn(
            store,
            session_id,
            provider,
            UserTurnInput(text="resumed task"),
            monkeypatch,
            display_spy,
        )
        assert [item["type"] for item in requests[0]["input"]] == [
            "user_input",
            "model_output",
            "user_input",
        ]
        if restore == "resume":
            provider = GoogleProvider(settings)
        _restore_history(
            provider, store, session_id, display_spy, restore, include_tool_history
        )

    items = _next_request_input(provider, monkeypatch, display_spy)
    assert [item["type"] for item in items] == [
        "user_input",
        "model_output",
        "user_input",
        "function_call",
        "function_result",
        "user_input",
    ]
    assert items[3]["id"] == items[4]["call_id"] == "recovery-tool"
    assert "recovered result" in json.dumps(items[4])
    assert items[-1]["content"] == [{"type": "text", "text": "continue"}]


@pytest.mark.parametrize("restore", ["resume", "refresh"])
@pytest.mark.parametrize("include_tool_history", [False, True])
@pytest.mark.parametrize("source_provider", ["openai", "google"])
@pytest.mark.parametrize("prompt", ["describe this", ""])
def test_failed_image_turn_restores_tools(
    tmp_path,
    monkeypatch,
    display_spy,
    restore,
    include_tool_history,
    source_provider,
    prompt,
):
    provider_type = GoogleProvider if source_provider == "google" else OpenAIProvider
    provider = provider_type(
        Settings(api_key="test", provider=source_provider, max_retries=0)
    )
    user_input = UserTurnInput(
        text=prompt,
        images=[
            ImageAttachment(
                path="chart.png",
                mime_type="image/png",
                data_base64="abcd",
                byte_count=4,
            )
        ],
    )
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), source_provider, "test-model")
        _record_failed_provider_turn(
            store, session_id, provider, user_input, monkeypatch, display_spy
        )
        assert store.list_messages(session_id)[0].content == user_turn_history_text(
            user_input
        )
        # OpenAI exercises Responses replay as well as the cross-provider fallback.
        restored_provider = OpenAIProvider(Settings(api_key="test", provider="openai"))
        _restore_history(
            restored_provider,
            store,
            session_id,
            display_spy,
            restore,
            include_tool_history,
        )

    items = _next_request_input(restored_provider, monkeypatch, display_spy)
    assert [item["call_id"] for item in items if "call_id" in item] == [
        "recovery-tool",
        "recovery-tool",
    ]
    assert "recovered result" in json.dumps(items)
    assert items[-1] == {"role": "user", "content": "continue"}


@pytest.mark.parametrize(
    ("status", "include_tool_history"),
    [("failed", False), ("failed", True), ("completed", True)],
)
@pytest.mark.parametrize(
    "prompt", ["describe this", "", "literal\n\n[attached images: example.png]"]
)
def test_image_turn_preserves_native_response_history(
    tmp_path, monkeypatch, display_spy, status, include_tool_history, prompt
):
    user_input = UserTurnInput(
        text=prompt,
        images=[
            ImageAttachment(
                path="chart.png",
                mime_type="image/png",
                data_base64="abcd",
                byte_count=4,
            )
        ],
    )
    input_item = {
        "role": "user",
        "content": [
            *([{"type": "input_text", "text": prompt}] if prompt else []),
            {"type": "input_image", "image_url": "https://example.test/chart.png"},
        ],
    }
    provider = OpenAIProvider(Settings(api_key="test", provider="openai"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), "openai", "test-model")
        run_id = _record_tool_turn(
            store,
            session_id,
            prompt,
            status=status,
            final_answer=status == "completed",
            history_prompt=user_turn_history_text(user_input),
            request_input=[input_item],
        )
        _restore_history(
            provider, store, session_id, display_spy, "resume", include_tool_history
        )

    items = _next_request_input(provider, monkeypatch, display_spy)
    # Unredacted image input should use the native replay path, not the
    # generic fallback that restores the decorated persisted message.
    assert items[0] == input_item
    assert [item["call_id"] for item in items if "call_id" in item] == [run_id, run_id]
    assert items[-1] == {"role": "user", "content": "continue"}


@pytest.mark.parametrize("restore", ["resume", "refresh"])
@pytest.mark.parametrize("source_provider", ["openai", "anthropic"])
@pytest.mark.parametrize("include_tool_history", [False, True])
@pytest.mark.parametrize("checkpoint_status", ["completed", "started", "failed"])
def test_checkpoint_turn_recovery_uses_run_association(
    tmp_path,
    monkeypatch,
    display_spy,
    restore,
    source_provider,
    include_tool_history,
    checkpoint_status,
):
    provider = OpenAIProvider(Settings(api_key="test", provider="openai"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), source_provider, "test-model")
        first_run = _record_tool_turn(
            store, session_id, "first task", provider=source_provider
        )
        checkpoint_run = _record_tool_turn(
            store,
            session_id,
            "second task",
            # Repeating the initial prompt must not steal the run association.
            checkpoints=("second task", "also check tests"),
            status=checkpoint_status,
            provider=source_provider,
            final_answer=checkpoint_status != "failed",
        )
        # Exercise selective recovery even after a later successful turn.
        _record_tool_turn(store, session_id, "later task", provider=source_provider)
        if restore == "resume":
            session_module._resume_session(
                provider=provider,
                store=store,
                session_id=session_id,
                session_usage=TokenUsage(),
                display=display_spy,
                replay_history=False,
                include_tool_history=include_tool_history,
            )
        else:
            session_module.refresh_provider_history_from_store(
                provider,
                store,
                session_id,
                reason="turn",
                include_tool_history=include_tool_history,
            )

    items = _next_request_input(provider, monkeypatch, display_spy)
    tool_calls = [
        item["call_id"] for item in items if item.get("type") == "function_call"
    ]
    assert tool_calls.count(first_run) == int(include_tool_history)
    assert tool_calls.count(checkpoint_run) == int(
        include_tool_history or checkpoint_status == "failed"
    )
    assert len(tool_calls) == (
        3 if include_tool_history else int(checkpoint_status == "failed")
    )
    outputs = [
        item["call_id"] for item in items if item.get("type") == "function_call_output"
    ]
    assert outputs == tool_calls
    text = json.dumps(items)
    assert text.count("Answer: first task") == 1
    assert text.count("Answer: second task") == int(checkpoint_status != "failed")
    assert text.count("Answer: later task") == 1
    assert text.count("also check tests") == 1
    assert items[-1] == {"role": "user", "content": "continue"}
    if not include_tool_history and checkpoint_status != "failed":
        assert items == [
            {"role": "user", "content": "first task"},
            {"role": "assistant", "content": "Answer: first task"},
            {"role": "user", "content": "second task"},
            {"role": "user", "content": "second task"},
            {"role": "user", "content": "also check tests"},
            {"role": "assistant", "content": "Answer: second task"},
            {"role": "user", "content": "later task"},
            {"role": "assistant", "content": "Answer: later task"},
            {"role": "user", "content": "continue"},
        ]


@pytest.mark.parametrize("source_provider", ["openai", "anthropic"])
@pytest.mark.parametrize("include_tool_history", [False, True])
@pytest.mark.parametrize("checkpoints", [(), ("also check tests", "check lint")])
@pytest.mark.parametrize("restore", ["resume", "refresh"])
def test_compaction_bounds_unfinished_tool_replay(
    tmp_path,
    monkeypatch,
    display_spy,
    source_provider,
    include_tool_history,
    checkpoints,
    restore,
):
    settings = Settings(
        api_key="test",
        provider="openai",
        compact_tool_output_max_chars=20,
    )
    provider = OpenAIProvider(settings)
    compaction_requests = []
    large_output = "x" * 30_000

    class SummaryProvider:
        def request_turn(self, **kwargs):
            compaction_requests.append(kwargs["user_message"])
            return CompletedResponse(
                response_id="summary",
                text="A short summary.",
                usage=TokenUsage(),
            )

    @contextmanager
    def open_summary_provider(*_args, **_kwargs):
        yield SummaryProvider()

    monkeypatch.setattr(
        session_module, "_open_compaction_provider", open_summary_provider
    )
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), source_provider, "test-model")
        run_id = _record_tool_turn(
            store,
            session_id,
            "active task",
            status="started",
            final_answer=False,
            tool_output=large_output,
            provider=source_provider,
            checkpoints=checkpoints,
        )
        session_module._compact_live_session(
            provider=provider,
            store=store,
            session_id=session_id,
            runtime=session_module._runtime_from_settings(settings),
            display=display_spy,
            session_usage=TokenUsage(),
            reason="auto",
            pending_tool_calls=[
                ToolCall(call_id=run_id, name="shell", arguments={"command": "pwd"})
            ],
            pending_tool_result_items=[
                {
                    "type": "function_call_output",
                    "call_id": run_id,
                    "output": large_output,
                }
            ],
        )
        assert large_output not in compaction_requests[0]
        assert "original_chars=30000, kept_chars=20" in compaction_requests[0]
        items = _next_request_input(provider, monkeypatch, display_spy)
        surviving_prompts = list(checkpoints) or ["active task"]
        assert [item["role"] for item in items] == [
            "assistant",
            *(["user"] * (len(surviving_prompts) + 1)),
        ]
        assert [item["content"] for item in items[1:-1]] == surviving_prompts
        assert "A short summary." in items[0]["content"]
        assert large_output not in json.dumps(items)

        # A restart must not reintroduce the summarized portion of the same run.
        for new_work in (False, True):
            if new_work:
                store.add_observability_event(
                    run_session_id=run_id,
                    session_id=session_id,
                    step_index=3,
                    event_type="model_call",
                    request_payload={"input": "Resume after compaction"},
                    response_payload={
                        "output": [
                            {
                                "type": "function_call",
                                "call_id": "after-compaction",
                                "name": "shell",
                                "arguments": '{"command":"pwd"}',
                            }
                        ]
                    },
                    success=True,
                )
                store.add_observability_event(
                    run_session_id=run_id,
                    session_id=session_id,
                    step_index=4,
                    event_type="tool_call",
                    tool_call_id="after-compaction",
                    tool_name="shell",
                    tool_input={"command": "pwd"},
                    tool_output="new result",
                    success=True,
                )
                store.add_observability_event(
                    run_session_id=run_id,
                    session_id=session_id,
                    step_index=5,
                    event_type="model_call",
                    request_payload={
                        "input": [
                            {
                                "type": "function_call_output",
                                "call_id": "after-compaction",
                                "output": "new result",
                            }
                        ]
                    },
                    response_payload={"error": {"message": "Bad Request"}},
                    success=False,
                    status_code=400,
                )
                store.update_run_session(
                    run_id,
                    status="failed",
                    ended_at=store.list_observability_events(run_session_id=run_id)[
                        -1
                    ].timestamp,
                )
            resumed_provider = OpenAIProvider(settings)
            _restore_history(
                resumed_provider,
                store,
                session_id,
                display_spy,
                restore,
                include_tool_history,
            )
            restored = _next_request_input(resumed_provider, monkeypatch, display_spy)
            assert large_output not in json.dumps(restored)
            assert run_id not in json.dumps(restored)
            assert [item["call_id"] for item in restored if "call_id" in item] == (
                ["after-compaction", "after-compaction"] if new_work else []
            )
            assert [
                item["content"] for item in restored if item.get("role") == "user"
            ] == [*surviving_prompts, "continue"]


@pytest.mark.parametrize("include_tool_history", [False, True])
def test_missing_initial_prompt_without_compaction_does_not_use_checkpoint_fallback(
    tmp_path, monkeypatch, display_spy, include_tool_history
):
    provider = OpenAIProvider(Settings(api_key="test", provider="openai"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), "openai", "test-model")
        _record_tool_turn(
            store,
            session_id,
            "discarded task",
            checkpoints=("checkpoint",),
            status="failed",
            final_answer=False,
        )
        store.delete_message(store.list_messages(session_id)[0].id)
        _restore_history(
            provider, store, session_id, display_spy, "resume", include_tool_history
        )

    assert _next_request_input(provider, monkeypatch, display_spy) == [
        {"role": "user", "content": "checkpoint"},
        {"role": "user", "content": "continue"},
    ]


@pytest.mark.parametrize("include_tool_history", [False, True])
def test_repeated_checkpoint_text_does_not_consume_the_next_run(
    tmp_path, monkeypatch, display_spy, include_tool_history
):
    provider = OpenAIProvider(Settings(api_key="test", provider="openai"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), "openai", "test-model")
        completed_run = _record_tool_turn(
            store, session_id, "continue", checkpoints=("continue",)
        )
        failed_run = _record_tool_turn(
            store, session_id, "continue", status="failed", final_answer=False
        )
        session_module._resume_session(
            provider=provider,
            store=store,
            session_id=session_id,
            session_usage=TokenUsage(),
            display=display_spy,
            replay_history=False,
            include_tool_history=include_tool_history,
        )

    items = _next_request_input(provider, monkeypatch, display_spy)
    call_ids = [item["call_id"] for item in items if "call_id" in item]
    assert call_ids == (
        [completed_run, completed_run] if include_tool_history else []
    ) + [failed_run, failed_run]
    user_texts = [item["content"] for item in items if item.get("role") == "user"]
    assert user_texts == ["continue"] * 4


@pytest.mark.parametrize("restore", ["resume", "refresh"])
@pytest.mark.parametrize("include_tool_history", [False, True])
@pytest.mark.parametrize("source_provider", ["openai", "anthropic"])
@pytest.mark.parametrize("persist_before_run", [False, True])
def test_forked_repeated_prompt_tools_attach_to_the_new_run(
    tmp_path,
    monkeypatch,
    display_spy,
    restore,
    include_tool_history,
    source_provider,
    persist_before_run,
):
    provider = OpenAIProvider(Settings(api_key="test", provider="openai"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        original_id = store.create_session(str(tmp_path), source_provider, "test-model")
        original_run = _record_tool_turn(
            store, original_id, "continue", provider=source_provider
        )
        session_id = store.fork_session(
            original_id, store.list_messages(original_id)[-1].id
        )
        assert not store.list_run_sessions(session_id)
        failed_run = _record_tool_turn(
            store,
            session_id,
            "continue",
            provider=source_provider,
            status="failed",
            final_answer=False,
            checkpoints=("continue",),
            persist_before_run=persist_before_run,
        )
        _restore_history(
            provider, store, session_id, display_spy, restore, include_tool_history
        )

    items = _next_request_input(provider, monkeypatch, display_spy)
    assert items[:3] == [
        {"role": "user", "content": "continue"},
        {"role": "assistant", "content": "Answer: continue"},
        {"role": "user", "content": "continue"},
    ]
    assert [item["call_id"] for item in items if "call_id" in item] == [
        failed_run,
        failed_run,
    ]
    assert original_run not in json.dumps(items)
    assert [item["content"] for item in items if item.get("role") == "user"] == [
        "continue"
    ] * 4


@pytest.mark.parametrize("restore", ["resume", "refresh"])
@pytest.mark.parametrize("include_tool_history", [False, True])
@pytest.mark.parametrize("source_provider", ["google", "openai"])
@pytest.mark.parametrize(
    "checkpoints", [("check tests",), ("check tests", "check lint")]
)
def test_compaction_wrapped_checkpoint_recovers_only_unsummarized_tools(
    tmp_path,
    monkeypatch,
    display_spy,
    restore,
    include_tool_history,
    source_provider,
    checkpoints,
):
    settings = Settings(
        api_key="test",
        provider=source_provider,
        max_retries=0,
        compact_tail_turns=0,
    )
    google = source_provider == "google"
    provider_type = GoogleProvider if google else OpenAIProvider
    provider = provider_type(settings)
    requests = []

    def urlopen(request, timeout):
        del timeout
        requests.append(json.loads(request.data))
        if len(requests) > 2:
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {},
                io.BytesIO(b'{"error":{"message":"failed after compaction"}}'),
            )
        call_id = "before-compaction" if len(requests) == 1 else "after-compaction"
        return io.BytesIO(
            json.dumps(
                {
                    "id": f"{call_id}-response",
                    "outputs" if google else "output": [
                        {
                            "type": "function_call",
                            "id" if google else "call_id": call_id,
                            "name": "shell",
                            "arguments": (
                                {"command": "pwd"} if google else '{"command":"pwd"}'
                            ),
                        }
                    ],
                }
            ).encode()
        )

    def execute_tools(response, *, tracer, **_kwargs):
        call_id = response.function_calls[0].call_id
        output = (
            "old tool output" if call_id == "before-compaction" else "new tool output"
        )
        tracer.log_tool_call(
            tool_name="shell",
            tool_call_id=call_id,
            tool_input={"command": "pwd"},
            tool_output=output,
            duration_ms=1,
            success=True,
        )
        return [
            {
                "type": "function_result" if google else "function_call_output",
                "call_id": call_id,
                "name": "shell",
                "result" if google else "output": output,
            }
        ], False

    class SummaryProvider:
        def request_turn(self, **_kwargs):
            return CompletedResponse(
                response_id="summary", text="A short summary.", usage=TokenUsage()
            )

    @contextmanager
    def open_summary_provider(*_args, **_kwargs):
        yield SummaryProvider()

    compact_at_iteration = iter([True, False])
    checkpoint_batches = iter([[QueuedInput(text=text) for text in checkpoints], []])
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(provider, "execute_tool_calls", execute_tools)
    monkeypatch.setattr(
        session_module, "_open_compaction_provider", open_summary_provider
    )
    monkeypatch.setattr(
        session_module,
        "_should_auto_compact",
        lambda **_kwargs: next(compact_at_iteration),
    )
    # Exercise local compaction for both replay formats, irrespective of the
    # selected Responses model's native compaction capability.
    monkeypatch.setattr(
        session_module, "_provider_has_server_side_compaction", lambda _provider: False
    )
    monkeypatch.setattr(
        display_spy,
        "drain_checkpoint_follow_ups",
        lambda: next(checkpoint_batches),
        raising=False,
    )
    monkeypatch.setattr(display_spy, "debug", lambda _message: None, raising=False)
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path), source_provider, settings.model
        )
        tracer = RunTracer.start(
            store=store,
            session_id=session_id,
            agent_name="main",
            agent_type="session_turn",
            provider=source_provider,
            provider_id=None,
            profile_id=None,
            model=settings.model,
        )
        store.add_message(session_id, "user", "initial task")
        response = provider.request_turn(
            user_message="initial task",
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
            tracer=tracer,
        )
        with pytest.raises(RuntimeError, match="400"):
            session_module._run_tool_iterations(
                provider=provider,
                response=response,
                max_workers=1,
                display=display_spy,
                session_usage=TokenUsage(),
                turn_usage=TokenUsage(),
                store=store,
                session_id=session_id,
                current_user_turn_text="initial task",
                tracer=tracer,
            )
        tracer.finish(status="failed", usage=TokenUsage())
        assert [
            message.content
            for message in store.list_messages(session_id)
            if message.role == "user"
        ] == list(checkpoints)
        wrapped_checkpoint = (
            f"{session_module._compaction_continuation_prompt('initial task')}\n\n"
            "User follow-up for the current turn:\n" + "\n\n".join(checkpoints)
        )
        assert json.dumps(wrapped_checkpoint) in json.dumps(requests[1])
        if restore == "resume":
            provider = provider_type(settings)
        _restore_history(
            provider, store, session_id, display_spy, restore, include_tool_history
        )

    items = _next_request_input(provider, monkeypatch, display_spy)
    tool_items = [
        item
        for item in items
        if item.get("type")
        in {"function_call", "function_result", "function_call_output"}
    ]
    assert len(tool_items) == 2
    assert tool_items[0].get("call_id", tool_items[0].get("id")) == "after-compaction"
    assert tool_items[1]["call_id"] == "after-compaction"
    text = json.dumps(items)
    assert "new tool output" in text
    assert "before-compaction" not in text
    assert "old tool output" not in text
    assert "initial task" not in text
    assert "A short summary." in text
    for checkpoint in checkpoints:
        assert text.count(checkpoint) == 1
