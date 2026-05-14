import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAllRuns, fetchRunFilterValues } from "../../api";
import { renderWithProviders } from "../../test/render";
import type { AllRunsRun } from "../../types";
import { RunsTable } from "./RunsTable";

vi.mock("../../api", () => ({
  fetchAllRuns: vi.fn(),
  fetchRunFilterValues: vi.fn(),
}));

const fetchAllRunsMock = vi.mocked(fetchAllRuns);
const fetchRunFilterValuesMock = vi.mocked(fetchRunFilterValues);

function makeRun(overrides: Partial<AllRunsRun> = {}): AllRunsRun {
  return {
    run_session_id: "run-1",
    session_id: "session-1",
    parent_run_session_id: null,
    agent_name: "agent",
    agent_type: "default",
    provider: "openai",
    provider_id: "openai",
    profile_id: "default",
    model: "gpt-4.1",
    status: "started",
    started_at: "2026-05-13T12:00:00Z",
    ended_at: null,
    total_duration_ms: 1_200,
    input_tokens: 10,
    cached_input_tokens: 0,
    cache_write_tokens: 0,
    cache_write_1h_tokens: 0,
    output_tokens: 20,
    reasoning_tokens: 0,
    provider_total_tokens: 30,
    estimated_cost_usd: 0.01,
    total_tool_calls: 1,
    total_api_calls: 2,
    error_count: 0,
    metadata: {},
    session_title: "Dashboard run",
    ...overrides,
  };
}

describe("RunsTable", () => {
  beforeEach(() => {
    fetchAllRunsMock.mockResolvedValue({
      runs: [makeRun()],
      total_count: 1,
    });
    fetchRunFilterValuesMock.mockResolvedValue({
      statuses: ["completed", "failed", "started"],
      providers: ["anthropic", "openai"],
      models: ["claude-4", "gpt-4.1"],
    });
  });

  it("uses the shared app status badge styling for run statuses", async () => {
    renderWithProviders(<RunsTable scope="workspace" />);

    const status = await screen.findByText("started", {
      selector: "[data-slot='badge']",
    });

    expect(status).toHaveAttribute("data-variant", "running");
    expect(status).toHaveAttribute("data-size", "meta");
    expect(status).toHaveClass("runs-row__status");
  });

  it("loads filter options from the distinct database values endpoint", async () => {
    renderWithProviders(<RunsTable startDate="2026-05-01" endDate="2026-05-14T23:59:59" scope="workspace" />);

    expect(await screen.findByRole("option", { name: "anthropic" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "claude-4" })).toBeInTheDocument();
    expect(fetchRunFilterValuesMock).toHaveBeenCalledWith({
      start_date: "2026-05-01",
      end_date: "2026-05-14T23:59:59",
      scope: "workspace",
    });
  });
});
