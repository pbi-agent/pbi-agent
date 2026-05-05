from __future__ import annotations

import importlib.util
from pathlib import Path

from pbi_agent.web.api.schemas.events import (
    MessageAddedSseEventModel,
    ToolGroupAddedSseEventModel,
    UsageUpdatedSseEventModel,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "generate_api_types.py"
SPEC = importlib.util.spec_from_file_location("generate_api_types", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load API type generator.")
generate_api_types = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_api_types)


def test_generated_api_types_are_current() -> None:
    assert (
        generate_api_types.OUTPUT.read_text(encoding="utf-8")
        == generate_api_types.render_api_types()
    )


def test_generated_api_types_include_sse_event_union() -> None:
    generated = generate_api_types.render_api_types()

    assert "export type SseEventModel =" in generated
    assert "InputStateSseEventModel" in generated
    assert "LiveSessionEndedSseEventModel" in generated
    assert "export type TokenUsagePayloadModel =" in generated
    assert "usage: TokenUsagePayloadModel" in generated
    assert 'role: "user" | "assistant" | "notice" | "error" | "debug"' in generated
    assert "export type ToolCallMetadataModel =" in generated


def test_high_value_sse_payload_schemas_match_emitted_shapes() -> None:
    usage = {
        "input_tokens": 1,
        "cached_input_tokens": 2,
        "cache_write_tokens": 3,
        "cache_write_1h_tokens": 4,
        "output_tokens": 5,
        "reasoning_tokens": 6,
        "tool_use_tokens": 7,
        "provider_total_tokens": 8,
        "sub_agent_input_tokens": 9,
        "sub_agent_output_tokens": 10,
        "sub_agent_reasoning_tokens": 11,
        "sub_agent_tool_use_tokens": 12,
        "sub_agent_provider_total_tokens": 13,
        "sub_agent_cost_usd": 0.01,
        "context_tokens": 14,
        "total_tokens": 15,
        "estimated_cost_usd": 0.02,
        "main_agent_total_tokens": 16,
        "sub_agent_total_tokens": 17,
        "model": "gpt-5.4",
        "service_tier": "default",
    }

    usage_event = UsageUpdatedSseEventModel.model_validate(
        {
            "seq": 1,
            "type": "usage_updated",
            "created_at": "2026-04-27T00:00:00Z",
            "payload": {
                "scope": "turn",
                "usage": usage,
                "elapsed_seconds": 1.5,
                "live_session_id": "live-1",
            },
        }
    )
    message_event = MessageAddedSseEventModel.model_validate(
        {
            "seq": 2,
            "type": "message_added",
            "created_at": "2026-04-27T00:00:01Z",
            "payload": {
                "item_id": "message-1",
                "role": "assistant",
                "content": "Done.",
                "markdown": True,
                "message_id": "msg-1",
                "file_paths": [],
                "image_attachments": [],
            },
        }
    )
    tool_event = ToolGroupAddedSseEventModel.model_validate(
        {
            "seq": 3,
            "type": "tool_group_added",
            "created_at": "2026-04-27T00:00:02Z",
            "payload": {
                "item_id": "tool-group-1",
                "label": "Tool calls",
                "status": "completed",
                "items": [
                    {
                        "text": "ok",
                        "metadata": {
                            "tool_name": "shell",
                            "path": "README.md",
                            "success": True,
                            "diff_line_numbers": [{"old": 1, "new": 2}],
                            "timeout_ms": "1000",
                            "exit_code": 0,
                        },
                    }
                ],
            },
        }
    )

    assert usage_event.payload.usage.total_tokens == 15
    assert message_event.payload.role == "assistant"
    assert tool_event.payload.items[0].metadata is not None
    assert tool_event.payload.items[0].metadata.tool_name == "shell"


def test_generated_api_types_include_operation_contracts() -> None:
    generated = generate_api_types.render_api_types()

    assert "export type ApiOperationResponses =" in generated
    assert '"GET /api/bootstrap": BootstrapResponse' in generated
    assert (
        '"POST /api/sessions/{session_id}/messages": LiveSessionResponse' in generated
    )
    assert "export type ApiJsonRequestBodies =" in generated
    assert '"POST /api/sessions": CreateSessionRequest' in generated
    assert '"PATCH /api/tasks/{task_id}": UpdateTaskRequest' in generated
    assert "export type ApiOperationPathParams =" in generated
    assert '"GET /api/runs/{run_session_id}": { run_session_id: string }' in generated
    assert "export type ApiOperationQueryParams =" in generated
    assert '"GET /api/files/search": { q?: string; limit?: number }' in generated


def test_generated_api_unknown_responses_are_limited_to_streams_and_files() -> None:
    generated = generate_api_types.render_api_types()
    unknown_operations = {
        line.split(":", 1)[0].strip()
        for line in generated.splitlines()
        if line.strip().endswith(": unknown;")
    }

    assert unknown_operations == {
        '"GET /api/events/sessions/{session_id}"',
        '"GET /api/events/{stream_id}"',
        '"GET /api/uploads/{upload_id}"',
    }
