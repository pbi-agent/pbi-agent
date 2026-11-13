import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { fetchRunDetail, fetchRunEvent } from "../../api";
import { RunDetailModal } from "./RunDetailModal";
import type { ObservabilityEvent, ObservabilityEventSummary, RunSession } from "../../types";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    fetchRunDetail: vi.fn(),
    fetchRunEvent: vi.fn(),
  };
});

const mockFetchRunDetail = vi.mocked(fetchRunDetail);
const mockFetchRunEvent = vi.mocked(fetchRunEvent);

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

function makeEvent(overrides: Partial<ObservabilityEventSummary>): ObservabilityEventSummary {
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
    tool_name: null,
    tool_call_id: null,
    tool_duration_ms: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: 3,
    cached_input_tokens: null,
    reasoning_tokens: null,
    status_code: null,
    success: true,
    error_message: null,
    has_payload: false,
    ...overrides,
  };
}

/** The full event the payload endpoint returns for a listed event. */
function withPayloads(
  event: ObservabilityEventSummary,
  payloads: Partial<ObservabilityEvent>,
): ObservabilityEvent {
  return {
    ...event,
    request_config: null,
    request_payload: null,
    response_payload: null,
    tool_input: null,
    tool_output: null,
    metadata: null,
    ...payloads,
  };
}

describe("RunDetailModal", () => {
  beforeEach(() => {
    mockFetchRunDetail.mockReset();
    mockFetchRunEvent.mockReset();
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
      child_runs: [],
      events: [
        makeEvent({ step_index: 0, event_type: "run_start" }),
        makeEvent({ step_index: 1, event_type: "agent_step_start" }),
        makeEvent({ step_index: 2, event_type: "model_call", model: "gpt-5.4-mini", duration_ms: 736 }),
        makeEvent({ step_index: 3, event_type: "tool_call", tool_name: "shell", duration_ms: 12_300 }),
        makeEvent({ step_index: 4, event_type: "agent_step_end" }),
        makeEvent({ step_index: 5 }),
      ],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const status = (await screen.findByText("completed")).closest('[data-slot="badge"]');
    expect(status).toHaveAttribute("data-variant", "completed");
    expect(status).toHaveAttribute("data-size", "meta");
    expect(status).toHaveAttribute("data-run-status");
    expect(screen.getByText("Trace (3)")).toBeInTheDocument();
    expect(screen.getAllByText("gpt-5.4")).toHaveLength(1);

    const spans = document.querySelectorAll('[data-slot="trace-span"]');
    expect(Array.from(spans, (span) => span.getAttribute("data-span-type"))).toEqual([
      "agent",
      "chat",
      "tool",
    ]);
    expect(spans[0]).toHaveAttribute("data-root");
    expect(spans[0]).toHaveTextContent("Agent");
    expect(spans[0]).toHaveTextContent("1 s");
    expect(spans[1]).toHaveTextContent("gpt-5.4-mini");
    expect(spans[1]).toHaveTextContent("0.736 s");
    expect(spans[2]).toHaveTextContent("shell");
    expect(spans[2]).toHaveTextContent("12.3 s");
    expect(screen.getByText("Chat").closest('[data-slot="badge"]')).toHaveAttribute(
      "data-variant",
      "trace-chat",
    );
    expect(document.querySelectorAll('[data-slot="trace-bar"]')).toHaveLength(3);
  });

  it("shows the empty state when the run has no spans", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun(),
      child_runs: [],
      events: [makeEvent({ step_index: 0, event_type: "run_start" }), makeEvent({ step_index: 1 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    expect(await screen.findByText("No events recorded for this run.")).toBeInTheDocument();
  });

  it("collapses and expands child spans", async () => {
    const user = userEvent.setup();
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ agent_name: "main" }),
      child_runs: [],
      events: [makeEvent({ event_type: "tool_call", tool_name: "shell", duration_ms: 10 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const collapse = await screen.findByRole("button", { name: "Collapse main" });
    expect(screen.getByText("shell")).toBeInTheDocument();

    await user.click(collapse);
    await waitFor(() => {
      expect(screen.queryByText("shell")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Expand main" }));
    expect(await screen.findByText("shell")).toBeInTheDocument();
  });

  it("nests a sub-agent run under the tool call that started it", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ agent_name: "main" }),
      events: [
        makeEvent({
          step_index: 1,
          event_type: "tool_call",
          tool_name: "sub_agent",
          tool_call_id: "call_1",
          duration_ms: 500,
        }),
      ],
      child_runs: [
        {
          parent_tool_call_id: "call_1",
          run: makeRun({
            run_session_id: "run-2",
            parent_run_session_id: "run-1",
            agent_name: "explorer",
            total_duration_ms: 400,
          }),
          events: [
            makeEvent({
              run_session_id: "run-2",
              step_index: 1,
              event_type: "tool_call",
              tool_name: "read_file",
              duration_ms: 20,
            }),
          ],
        },
      ],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    expect(await screen.findByText("Trace (4)")).toBeInTheDocument();
    const toolRow = screen.getByText("sub_agent").closest('[data-slot="collapsible"]');
    const childRow = screen.getByText("explorer").closest('[data-slot="collapsible"]');
    expect(toolRow).toContainElement(childRow as HTMLElement);
    expect(childRow).toContainElement(screen.getByText("read_file"));
    expect(screen.getByRole("button", { name: "Collapse sub_agent" })).toBeInTheDocument();
  });

  it("renders reasoning effort after the provider/model header segment", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({
        agent_name: "main",
        provider: "chatgpt",
        model: "gpt-5.5",
        reasoning_effort: "high",
      }),
      child_runs: [],
      events: [makeEvent({ step_index: 1 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const header = await screen.findByLabelText("Run summary");
    expect(header).toHaveTextContent("main·chatgpt/gpt-5.5·high");
  });

  it("omits empty or none reasoning effort from the provider/model header segment", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ reasoning_effort: "none" }),
      child_runs: [],
      events: [makeEvent({ step_index: 1 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const header = await screen.findByLabelText("Run summary");
    expect(header).toHaveTextContent("Agent·openai/gpt-5.4");
    expect(header).not.toHaveTextContent("none");
  });

  it("marks failed spans with the shared failed status badge", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "completed" }),
      child_runs: [],
      events: [
        makeEvent({ step_index: 1, event_type: "model_call", success: true, status_code: 200 }),
        makeEvent({
          step_index: 2,
          event_type: "tool_call",
          tool_name: "shell",
          success: false,
          error_message: "exit 1",
        }),
      ],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const failBadge = (await screen.findByText("fail")).closest('[data-slot="badge"]');
    expect(failBadge).toHaveAttribute("data-variant", "failed");
    expect(failBadge).toHaveAttribute("data-size", "meta");
    expect(failBadge?.closest('[data-slot="trace-span"]')).toHaveTextContent("shell");
    expect(screen.getAllByText("fail")).toHaveLength(1);
    expect(screen.queryByText("200")).not.toBeInTheDocument();
  });

  it("treats completed runs as terminal", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "completed", ended_at: "2026-04-27T10:00:01Z" }),
      child_runs: [],
      events: [makeEvent({ step_index: 1 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const status = (await screen.findByText("completed")).closest('[data-slot="badge"]');
    expect(status).toHaveAttribute("data-variant", "completed");
  });

  it("renders fatal errors from run detail", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "failed", fatal_error: "RuntimeError: boom" }),
      child_runs: [],
      events: [makeEvent({ step_index: 1, error_message: "RuntimeError: boom" })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    expect(await screen.findByText("failed")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError: boom")).toBeInTheDocument();
  });

  it("loads a span's payloads on demand and copies them", async () => {
    const user = userEvent.setup();
    const writeText = mockClipboardWrite();
    const toolInput = { command: "echo hi" };
    const toolEvent = makeEvent({
      step_index: 4,
      event_type: "tool_call",
      tool_name: "shell",
      has_payload: true,
    });
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "completed" }),
      child_runs: [],
      events: [toolEvent],
    });
    mockFetchRunEvent.mockResolvedValue(
      withPayloads(toolEvent, { tool_input: toolInput, tool_output: "done", metadata: {} }),
    );

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} scope="global" />);

    const row = await screen.findByRole("button", { name: /shell/ });
    expect(mockFetchRunEvent).not.toHaveBeenCalled();

    await user.click(row);
    const copyInput = await screen.findByRole("button", { name: "Copy Tool Input" });
    const copyOutput = screen.getByRole("button", { name: "Copy Tool Output" });
    expect(mockFetchRunEvent).toHaveBeenCalledWith("run-1", 4, "global");
    expect(screen.queryByText("Metadata")).not.toBeInTheDocument();

    expect(copyInput).toHaveAttribute("data-copy-status", "idle");
    expect(copyOutput).toHaveAttribute("data-copy-status", "idle");

    await user.click(copyInput);
    await user.click(copyOutput);

    await waitFor(() => {
      expect(writeText).toHaveBeenNthCalledWith(1, JSON.stringify(toolInput, null, 2));
      expect(writeText).toHaveBeenNthCalledWith(2, "done");
    });
  });

  it("shows an error message without fetching when the span has no payload", async () => {
    const user = userEvent.setup();
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun(),
      child_runs: [],
      events: [makeEvent({ event_type: "error", success: false, error_message: "boom" })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: /error/ }));
    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(mockFetchRunEvent).not.toHaveBeenCalled();
  });

  it("keeps nested row state when a parent span is collapsed and reopened", async () => {
    const user = userEvent.setup();
    const shellEvent = makeEvent({
      run_session_id: "run-2",
      step_index: 1,
      event_type: "tool_call",
      tool_name: "shell",
      has_payload: true,
    });
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ agent_name: "main" }),
      events: [makeEvent({ event_type: "tool_call", tool_name: "sub_agent", tool_call_id: "call_1" })],
      child_runs: [
        {
          parent_tool_call_id: "call_1",
          run: makeRun({ run_session_id: "run-2", parent_run_session_id: "run-1", agent_name: "explorer" }),
          events: [shellEvent],
        },
      ],
    });
    mockFetchRunEvent.mockResolvedValue(withPayloads(shellEvent, { tool_output: "done" }));

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: /shell/ }));
    expect(await screen.findByText("Tool Output")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Collapse explorer" }));
    await waitFor(() => expect(screen.queryByText("shell")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Collapse main" }));
    await waitFor(() => expect(screen.queryByText("sub_agent")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Expand main" }));

    // explorer is still collapsed; reopening it shows the payload still open.
    await user.click(await screen.findByRole("button", { name: "Expand explorer" }));
    expect(await screen.findByText("Tool Output")).toBeInTheDocument();
    expect(mockFetchRunEvent).toHaveBeenCalledTimes(1);
  });

  it("shows in-flight work for a running run instead of the empty state", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "running", ended_at: null, total_duration_ms: 3_000 }),
      child_runs: [],
      events: [
        makeEvent({ step_index: 0, event_type: "run_start", timestamp: "2026-04-27T10:00:00Z" }),
        makeEvent({
          step_index: 1,
          event_type: "model_call_start",
          timestamp: "2026-04-27T10:00:01Z",
          success: null,
        }),
      ],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    expect(await screen.findByText("Trace (2)")).toBeInTheDocument();
    expect(screen.queryByText("No events recorded for this run.")).not.toBeInTheDocument();
    const pending = screen.getByText("Chat").closest('[data-slot="trace-span"]');
    expect(pending).toHaveTextContent("running");
    expect(pending?.querySelector("[data-span-status]")).toHaveAttribute("data-variant", "running");
  });

  it("treats interrupted runs as terminal", async () => {
    mockFetchRunDetail.mockResolvedValue({
      run: makeRun({ status: "interrupted", fatal_error: "Session interrupted." }),
      child_runs: [],
      events: [makeEvent({ step_index: 1 })],
    });

    renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    const status = (await screen.findByText("interrupted")).closest('[data-slot="badge"]');
    expect(status).toHaveAttribute("data-variant", "completed");
    expect(screen.getByText("Session interrupted.")).toBeInTheDocument();
  });

  it("refetches when a viewed running run query is invalidated", async () => {
    mockFetchRunDetail
      .mockResolvedValueOnce({
        run: makeRun({ status: "running", ended_at: null, total_duration_ms: null }),
        child_runs: [],
      events: [makeEvent({ event_type: "run_start" })],
      })
      .mockResolvedValueOnce({
        run: makeRun({ status: "completed" }),
        child_runs: [],
      events: [
          makeEvent({ event_type: "run_start" }),
          makeEvent({ step_index: 2, event_type: "model_call" }),
          makeEvent({ step_index: 3, event_type: "run_end" }),
        ],
      });

    const { queryClient } = renderWithProviders(<RunDetailModal runSessionId="run-1" onClose={vi.fn()} />);

    expect(await screen.findByText("running")).toBeInTheDocument();

    await queryClient.invalidateQueries({ queryKey: ["run-detail"] });

    await waitFor(() => {
      expect(screen.getByText("completed")).toBeInTheDocument();
      expect(screen.getByText("Trace (2)")).toBeInTheDocument();
    });
  });
});
