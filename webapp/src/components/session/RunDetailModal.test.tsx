import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

function mockClipboardWrite() {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  return writeText;
}

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
    reasoning_effort: null,
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

  afterEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined,
    });
  });

  it("renders final status and event count from run detail", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "completed" }),
      events: [makeEvent({ step_index: 1 }), makeEvent({ step_index: 2, event_type: "agent_step_end" })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const status = await screen.findByText("completed");
    expect(status).toHaveAttribute("data-variant", "completed");
    expect(status).toHaveAttribute("data-size", "meta");
    expect(status).toHaveClass("run-header__status");
    expect(screen.getByText("Events (2)")).toBeInTheDocument();
    expect(screen.getAllByText("gpt-5.4")).toHaveLength(1);
  });

  it("renders reasoning effort after the provider/model header segment", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({
        agent_name: "main",
        provider: "chatgpt",
        model: "gpt-5.5",
        reasoning_effort: "high",
      }),
      events: [makeEvent({ step_index: 1 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const header = await screen.findByLabelText("Run summary");
    expect(header).toHaveTextContent("main·chatgpt/gpt-5.5·high");
  });

  it("omits empty or none reasoning effort from the provider/model header segment", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ reasoning_effort: "none" }),
      events: [makeEvent({ step_index: 1 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const header = await screen.findByLabelText("Run summary");
    expect(header).toHaveTextContent("Agent·openai/gpt-5.4");
    expect(header).not.toHaveTextContent("none");
  });

  it("uses shared status badge variants for event success without rendering status code chips", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "completed" }),
      events: [
        makeEvent({
          step_index: 1,
          event_type: "model_call",
          success: true,
          status_code: 200,
        }),
      ],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const okBadge = await screen.findByText("ok");
    expect(okBadge).toHaveAttribute("data-variant", "completed");
    expect(okBadge).toHaveAttribute("data-size", "meta");
    expect(okBadge).toHaveClass("event-row__status");
    expect(okBadge.querySelector('[data-slot="badge-dot"]')).toBeInTheDocument();
    expect(screen.queryByText("200")).not.toBeInTheDocument();
  });

  it("treats completed runs as terminal", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "completed", ended_at: "2026-04-27T10:00:01Z" }),
      events: [makeEvent({ step_index: 1 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const status = await screen.findByText("completed");
    expect(status).toHaveAttribute("data-variant", "completed");
  });

  it("renders fatal errors from run detail", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "failed", fatal_error: "RuntimeError: boom" }),
      events: [makeEvent({ step_index: 1, error_message: "RuntimeError: boom" })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    expect(await screen.findByText("failed")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError: boom")).toBeInTheDocument();
  });

  it("copies expanded input and output payload cards", async () => {
    const user = userEvent.setup();
    const writeText = mockClipboardWrite();
    const toolInput = { command: "echo hi" };
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "completed" }),
      events: [
        makeEvent({
          event_type: "tool_call",
          tool_name: "shell",
          tool_input: toolInput,
          tool_output: "done",
        }),
      ],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: /tool_call/ }));
    const copyInput = screen.getByRole("button", { name: "Copy Tool Input" });
    const copyOutput = screen.getByRole("button", { name: "Copy Tool Output" });

    expect(copyInput).toHaveClass("payload-section__copy");
    expect(copyOutput).toHaveClass("payload-section__copy");

    await user.click(copyInput);
    await user.click(copyOutput);

    await waitFor(() => {
      expect(writeText).toHaveBeenNthCalledWith(1, JSON.stringify(toolInput, null, 2));
      expect(writeText).toHaveBeenNthCalledWith(2, "done");
    });
  });

  it("treats interrupted runs as terminal", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "interrupted", fatal_error: "Session interrupted." }),
      events: [makeEvent({ step_index: 1 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const status = await screen.findByText("interrupted");
    expect(status).toHaveAttribute("data-variant", "completed");
    expect(screen.getByText("Session interrupted.")).toBeInTheDocument();
  });

  it("refetches when a viewed running run query is invalidated", async () => {
    mockFetchRunDetail
      .mockResolvedValueOnce({
        run: makeRun({ status: "running", ended_at: null, total_duration_ms: null }),
        events: [makeEvent({ event_type: "run_start" })],
      })
      .mockResolvedValueOnce({
        run: makeRun({ status: "completed" }),
        events: [makeEvent({ event_type: "run_start" }), makeEvent({ step_index: 2, event_type: "run_end" })],
      });

    const { queryClient } = renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    expect(await screen.findByText("running")).toBeInTheDocument();

    await queryClient.invalidateQueries({ queryKey: ["run-detail"] });

    await waitFor(() => {
      expect(screen.getByText("completed")).toBeInTheDocument();
      expect(screen.getByText("Events (2)")).toBeInTheDocument();
    });
  });
});
