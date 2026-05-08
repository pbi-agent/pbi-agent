import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { UsageBar } from "./UsageBar";
import type { UsagePayload } from "../../types";

function makeUsage(overrides: Partial<UsagePayload> = {}): UsagePayload {
  return {
    input_tokens: 0,
    cached_input_tokens: 0,
    cache_write_tokens: 0,
    cache_write_1h_tokens: 0,
    output_tokens: 0,
    reasoning_tokens: 0,
    tool_use_tokens: 0,
    provider_total_tokens: 0,
    sub_agent_input_tokens: 0,
    sub_agent_output_tokens: 0,
    sub_agent_reasoning_tokens: 0,
    sub_agent_tool_use_tokens: 0,
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

describe("UsageBar", () => {
  it("renders a donut gauge without text labels", () => {
    renderWithProviders(
      <UsageBar
        compactThreshold={200000}
        usage={makeUsage({
          context_tokens: 85000,
          total_tokens: 999,
          estimated_cost_usd: 12.34,
        })}
      />,
    );

    expect(screen.queryByText("Context")).not.toBeInTheDocument();
    expect(screen.queryByText("85.0k / 200.0k")).not.toBeInTheDocument();
    expect(screen.queryByText("$12.34")).not.toBeInTheDocument();

    const gauge = screen.getByRole("progressbar", { name: "Context window usage" });
    expect(gauge).toHaveAttribute("aria-valuenow", "43");
    expect(gauge.querySelector("svg")).toBeInTheDocument();
  });

  it("handles missing usage with an empty gauge", () => {
    renderWithProviders(<UsageBar compactThreshold={200000} usage={null} />);

    const gauge = screen.getByRole("progressbar", { name: "Context window usage" });
    expect(gauge).toHaveAttribute("aria-valuenow", "0");
    expect(gauge).toHaveAttribute(
      "aria-valuetext",
      "Context window usage unavailable",
    );
  });

  it("treats initial zero context usage as unavailable", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <UsageBar compactThreshold={200000} usage={makeUsage({ context_tokens: 0 })} />,
    );

    const gauge = screen.getByRole("progressbar", { name: "Context window usage" });
    expect(gauge).toHaveAttribute("aria-valuenow", "0");
    expect(gauge).toHaveAttribute(
      "aria-valuetext",
      "Context window usage unavailable",
    );

    await user.hover(gauge);
    await waitFor(() => {
      expect(screen.getByText("No response usage yet")).toBeInTheDocument();
    });
  });

  it("clamps visual progress at 100 while preserving real values in the tooltip", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <UsageBar
        compactThreshold={1000}
        usage={makeUsage({ context_tokens: 1250 })}
      />,
    );

    const gauge = screen.getByRole("progressbar", { name: "Context window usage" });
    expect(gauge).toHaveAttribute("aria-valuenow", "100");
    expect(gauge).toHaveAttribute(
      "aria-valuetext",
      "1,250 of 1,000 context tokens used",
    );

    await user.hover(gauge);
    await waitFor(() => {
      expect(screen.getAllByText("1,250").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("1,000").length).toBeGreaterThan(0);
    const metaNodes = screen.getAllByText(
      (_, node) =>
        node?.classList.contains("context-gauge__tooltip-meta") === true &&
        node?.textContent === "125.0% of compaction threshold",
    );
    expect(metaNodes.length).toBeGreaterThan(0);
  });

  it("shows current usage and threshold in the tooltip on hover", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <UsageBar
        compactThreshold={200000}
        usage={makeUsage({ context_tokens: 85000 })}
      />,
    );

    const gauge = screen.getByRole("progressbar", { name: "Context window usage" });
    await user.hover(gauge);

    await waitFor(() => {
      expect(screen.getAllByText("85,000").length).toBeGreaterThan(0);
    });
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveClass("context-gauge__tooltip-content");
    expect(tooltip).toHaveAttribute("data-app-tooltip");
    expect(tooltip).toHaveAttribute("data-placement", "bottom");
    expect(screen.getAllByText("200,000").length).toBeGreaterThan(0);
    const metaNodes = screen.getAllByText(
      (_, node) =>
        node?.classList.contains("context-gauge__tooltip-meta") === true &&
        node?.textContent === "42.5% of compaction threshold",
    );
    expect(metaNodes.length).toBeGreaterThan(0);
  });
});
