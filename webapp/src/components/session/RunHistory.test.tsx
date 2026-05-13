import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { fetchSessionRuns } from "../../api";
import { RunHistory } from "./RunHistory";
import type { RunSession } from "../../types";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    fetchSessionRuns: vi.fn(),
  };
});

const mockFetchSessionRuns = vi.mocked(fetchSessionRuns);

function makeRun(overrides: Partial<RunSession>): RunSession {
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
    provider_total_tokens: 3,
    estimated_cost_usd: 0,
    total_tool_calls: 0,
    total_api_calls: 1,
    error_count: 0,
    metadata: null,
    ...overrides,
  };
}

describe("RunHistory", () => {
  beforeEach(() => {
    mockFetchSessionRuns.mockReset();
  });

  it("updates the run count when the query is invalidated and refetched", async () => {
    mockFetchSessionRuns
      .mockResolvedValueOnce([makeRun({ run_session_id: "run-1" })])
      .mockResolvedValueOnce([
        makeRun({ run_session_id: "run-1" }),
        makeRun({ run_session_id: "run-2", started_at: "2026-04-27T10:01:00Z" }),
      ]);

    const { queryClient } = renderWithProviders(<RunHistory sessionId="session-1" />);

    const toggle = await screen.findByRole("button", { name: /toggle run history/i });
    expect(toggle).toHaveClass("session-topbar-control", "run-history__toggle");
    await waitFor(() => expect(toggle.querySelector(".run-history__label")).toHaveTextContent("1"));

    await queryClient.invalidateQueries({ queryKey: ["session-runs", "session-1"] });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /toggle run history/i }).querySelector(".run-history__label"),
      ).toHaveTextContent("2");
    });
  });

  it("refetches on open and shows newest run first with final status", async () => {
    const user = userEvent.setup();
    mockFetchSessionRuns
      .mockResolvedValueOnce([
        makeRun({
          run_session_id: "old-run",
          status: "running",
          started_at: "2026-04-27T10:00:00Z",
        }),
      ])
      .mockResolvedValueOnce([
        makeRun({
          run_session_id: "old-run",
          status: "completed",
          started_at: "2026-04-27T10:00:00Z",
        }),
        makeRun({
          run_session_id: "new-run",
          status: "completed",
          started_at: "2026-04-27T10:05:00Z",
          model: "gpt-5.5",
        }),
      ]);

    renderWithProviders(<RunHistory sessionId="session-1" />);

    const toggle = await screen.findByRole("button", { name: /toggle run history/i });
    await user.click(toggle);
    await waitFor(() => expect(toggle).toHaveAttribute("aria-expanded", "true"));

    await waitFor(() => expect(mockFetchSessionRuns).toHaveBeenCalledTimes(2));
    await screen.findByText(/gpt-5\.5/);

    const statuses = screen.getAllByText("completed");
    expect(statuses[0].closest("button")).toHaveTextContent("gpt-5.5");
  });

  it("shows duration in the header and a minimal model, tokens, and cost summary", async () => {
    const user = userEvent.setup();
    mockFetchSessionRuns.mockResolvedValue([
      makeRun({
        input_tokens: 100,
        output_tokens: 20,
        reasoning_tokens: 3,
        provider_total_tokens: 0,
        estimated_cost_usd: 0.8467,
        total_duration_ms: 65_000,
        total_api_calls: 4,
        total_tool_calls: 2,
        error_count: 1,
      }),
    ]);

    renderWithProviders(<RunHistory sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: /toggle run history/i }));

    const summary = await screen.findByText("gpt-5.4 · 123 tok · $0.85");
    const runButton = summary.closest("button");
    if (!runButton) throw new Error("Run summary button not found");
    expect(summary).not.toHaveAttribute("data-slot", "badge");
    expect(runButton).not.toHaveTextContent("openai");
    expect(runButton).not.toHaveTextContent("API");
    expect(runButton).not.toHaveTextContent("tools");
    expect(runButton).not.toHaveTextContent("err");
    expect(runButton).toHaveTextContent("1m5s");
  });

  it("shows completed runs as terminal completed-style runs", async () => {
    const user = userEvent.setup();
    mockFetchSessionRuns.mockResolvedValue([
      makeRun({
        run_session_id: "web-run",
        status: "completed",
        started_at: "2026-04-27T10:00:00Z",
      }),
    ]);

    renderWithProviders(<RunHistory sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: /toggle run history/i }));

    const status = await screen.findByText("completed");
    expect(status).toHaveAttribute("data-variant", "completed");
    expect(status).toHaveAttribute("data-size", "meta");
  });
});
