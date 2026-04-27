import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import { fetchRunDetail } from "../../api";
import { RunDetailModal } from "./RunDetailModal";
import type { ObservabilityEvent, RunSession } from "../../types";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    fetchRunDetail: vi.fn(),
  };
});

const mockFetchRunDetail = vi.mocked(fetchRunDetail);

function makeRun(overrides: Partial<RunSession> = {}): RunSession {
  return {
    run_session_id: "run-1",
    session_id: "session-1",
    parent_run_session_id: null,
    agent_name: "Agent",
    agent_type: "agent",
    provider: "openai",
    provider_id: "openai-main",
    profile_id: null,
    model: "gpt-5.4",
    status: "completed",
    started_at: "2026-04-27T10:00:00Z",
    ended_at: "2026-04-27T10:00:01Z",
    total_duration_ms: 1000,
    input_tokens: 1,
    cached_input_tokens: 0,
    cache_write_tokens: 0,
    cache_write_1h_tokens: 0,
    output_tokens: 2,
    reasoning_tokens: 0,
    tool_use_tokens: 0,
    provider_total_tokens: 3,
    estimated_cost_usd: 0,
    total_tool_calls: 0,
    total_api_calls: 1,
    error_count: 0,
    metadata: null,
    ...overrides,
  };
}

function makeEvent(overrides: Partial<ObservabilityEvent>): ObservabilityEvent {
  return {
    run_session_id: "run-1",
    session_id: "session-1",
    step_index: 1,
    event_type: "run_end",
    timestamp: "2026-04-27T10:00:01Z",
    duration_ms: 1000,
    provider: "openai",
    model: "gpt-5.4",
    url: null,
    request_config: null,
    request_payload: null,
    response_payload: null,
    tool_name: null,
    tool_call_id: null,
    tool_input: null,
    tool_output: null,
    tool_duration_ms: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: 3,
    status_code: null,
    success: true,
    error_message: null,
    metadata: null,
    ...overrides,
  };
}

describe("RunDetailModal", () => {
  beforeEach(() => {
    mockFetchRunDetail.mockReset();
  });

  it("renders final status and event count from run detail", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "completed" }),
      events: [makeEvent({ step_index: 1 }), makeEvent({ step_index: 2, event_type: "agent_step_end" })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    expect(await screen.findByText("completed")).toBeInTheDocument();
    expect(screen.getByText("Events (2)")).toBeInTheDocument();
  });

  it("refetches when a viewed running run query is invalidated", async () => {
    mockFetchRunDetail
      .mockResolvedValueOnce({
        run: makeRun({ status: "started", ended_at: null, total_duration_ms: null }),
        events: [makeEvent({ event_type: "run_start" })],
      })
      .mockResolvedValueOnce({
        run: makeRun({ status: "completed" }),
        events: [makeEvent({ event_type: "run_start" }), makeEvent({ step_index: 2, event_type: "run_end" })],
      });

    const { queryClient } = renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    expect(await screen.findByText("started")).toBeInTheDocument();

    await queryClient.invalidateQueries({ queryKey: ["run-detail"] });

    await waitFor(() => {
      expect(screen.getByText("completed")).toBeInTheDocument();
      expect(screen.getByText("Events (2)")).toBeInTheDocument();
    });
  });
});
