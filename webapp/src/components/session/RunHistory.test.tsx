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
    await waitFor(() => expect(toggle).toHaveTextContent("Runs (1)"));

    await queryClient.invalidateQueries({ queryKey: ["session-runs", "session-1"] });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /toggle run history/i })).toHaveTextContent("Runs (2)");
    });
  });

  it("refetches on open and shows newest run first with final status", async () => {
    const user = userEvent.setup();
    mockFetchSessionRuns
      .mockResolvedValueOnce([
        makeRun({
          run_session_id: "old-run",
          status: "started",
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

    await waitFor(() => expect(mockFetchSessionRuns).toHaveBeenCalledTimes(2));
    await screen.findByText("gpt-5.5");

    const statuses = screen.getAllByText("completed");
    expect(statuses[0].closest("button")).toHaveTextContent("gpt-5.5");
  });
});
