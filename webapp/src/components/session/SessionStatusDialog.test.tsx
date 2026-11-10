import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { fetchSessionRuns } from "../../api";
import type { UsagePayload, RunSession } from "../../types";
import { SessionStatusDialog } from "./SessionStatusDialog";

vi.mock("../../api", () => ({ fetchSessionRuns: vi.fn() }));

function makeUsage(overrides: Partial<UsagePayload> = {}): UsagePayload {
  return {
    input_tokens: 0,
    cached_input_tokens: 0,
    cache_write_tokens: 0,
    cache_write_1h_tokens: 0,
    output_tokens: 0,
    reasoning_tokens: 0,
    provider_total_tokens: 0,
    sub_agent_input_tokens: 0,
    sub_agent_output_tokens: 0,
    sub_agent_reasoning_tokens: 0,
    sub_agent_provider_total_tokens: 0,
    sub_agent_cost_usd: 0,
    context_tokens: 0,
    total_tokens: 0,
    estimated_cost_usd: 0,
    main_agent_total_tokens: 0,
    sub_agent_total_tokens: 0,
    model: "gpt-5.4",
    service_tier: "",
    ...overrides,
  };
}


describe("SessionStatusDialog", () => {
  beforeEach(() => { vi.mocked(fetchSessionRuns).mockReset().mockResolvedValue([]); });

  it("uses canonical totals and shows cache, context, and sub-agent usage", async () => {
    renderWithProviders(<SessionStatusDialog sessionId="session-1" compactThreshold={200000}
      usage={makeUsage({ input_tokens: 1000, cached_input_tokens: 500, output_tokens: 200,
        reasoning_tokens: 50, total_tokens: 1200, main_agent_total_tokens: 900,
        sub_agent_total_tokens: 300, estimated_cost_usd: 0.0123, sub_agent_cost_usd: 0.002,
        context_tokens: 80000 })} onClose={() => {}} />);
    expect(screen.getByText("1,200")).toBeInTheDocument();
    expect(screen.queryByText("1,250")).not.toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("$0.0123")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Agents" })).getByText("300")).toBeInTheDocument();
    expect(screen.getByText("80,000")).toBeInTheDocument();
    await screen.findByText("Runs");
    expect(fetchSessionRuns).toHaveBeenCalledWith("session-1");
  });

  it("handles a draft with no usage without fetching or displaying NaN", () => {
    renderWithProviders(<SessionStatusDialog sessionId={null} compactThreshold={null} usage={null} onClose={() => {}} />);
    expect(screen.getByText(/No usage yet/)).toBeInTheDocument();
    expect(screen.queryByText(/NaN|Infinity/)).not.toBeInTheDocument();
    expect(fetchSessionRuns).not.toHaveBeenCalled();
  });

  it("sums recorded activity and allows closing", async () => {
    const onClose = vi.fn();
    vi.mocked(fetchSessionRuns).mockResolvedValue([
      { total_api_calls: 2, total_tool_calls: 3, error_count: 0 },
      { total_api_calls: 5, total_tool_calls: 8, error_count: 1 },
    ] as RunSession[]);
    renderWithProviders(<SessionStatusDialog sessionId="session-1" compactThreshold={null} usage={null} onClose={onClose} />);
    const activity = screen.getByRole("region", { name: "Recorded activity" });
    expect(await within(activity).findByText("7")).toBeInTheDocument();
    expect(within(activity).getByText("11")).toBeInTheDocument();
    await userEvent.setup().keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("shows an activity error without hiding usage and supports retry", async () => {
    vi.mocked(fetchSessionRuns).mockRejectedValueOnce(new Error("offline"));
    renderWithProviders(<SessionStatusDialog sessionId="session-1" compactThreshold={null}
      usage={makeUsage({ total_tokens: 1234 })} onClose={() => {}} />);
    expect(await screen.findByText("Could not load recorded activity.")).toBeInTheDocument();
    expect(screen.getByText("1,234")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Runs")).toBeInTheDocument();
  });
});
