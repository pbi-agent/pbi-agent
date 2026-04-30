import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SessionWelcome } from "./SessionWelcome";

describe("SessionWelcome", () => {
  it("renders the live indicator, heading, and description", () => {
    render(<SessionWelcome />);

    const live = screen.getByLabelText("Session is live");
    expect(live).toHaveClass("status-pill", "status-pill--running");

    expect(
      screen.getByText(/agent's reasoning, tool calls, and replies/i),
    ).toBeInTheDocument();
  });

  it("lists the composer hints with their keyboard hints", () => {
    render(<SessionWelcome />);

    const tipsList = screen.getByRole("list");
    const tips = within(tipsList).getAllByRole("listitem");
    expect(tips).toHaveLength(4);

    expect(within(tips[0]).getByText("Send any prompt to begin")).toBeInTheDocument();
    expect(within(tips[0]).queryByRole("note")).toBeNull();

    const slashTip = tips.find((tip) =>
      within(tip).queryByText("Insert a saved command"),
    );
    expect(slashTip).toBeDefined();
    expect(slashTip!.querySelector("kbd")).toHaveTextContent("/");

    const shellTip = tips.find((tip) =>
      within(tip).queryByText("Run a shell command"),
    );
    expect(shellTip).toBeDefined();
    expect(shellTip!.querySelector("kbd")).toHaveTextContent("!");

    const mentionTip = tips.find((tip) =>
      within(tip).queryByText("Reference a workspace file"),
    );
    expect(mentionTip).toBeDefined();
    expect(mentionTip!.querySelector("kbd")).toHaveTextContent("@");
  });

  it("uses a polite live region so assistive tech announces it", () => {
    render(<SessionWelcome />);

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
  });
});
