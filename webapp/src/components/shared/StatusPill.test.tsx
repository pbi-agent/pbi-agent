import { render, screen } from "@testing-library/react";
import { StatusPill } from "./StatusPill";

const cases = [
  ["running", "running"],
  ["started", "running"],
  ["starting", "running"],
  ["waiting_for_input", "running"],
  ["completed", "completed"],
  ["interrupted", "completed"],
  ["ended", "completed"],
  ["failed", "failed"],
  ["idle", "secondary"],
] as const;

describe("StatusPill", () => {
  it.each(cases)("maps %s to the %s Badge variant", (status, variant) => {
    render(<StatusPill status={status} />);

    expect(screen.getByText(status)).toHaveAttribute("data-variant", variant);
  });

  it("can render with shared metadata badge sizing", () => {
    render(<StatusPill status="started" size="meta" className="run-card__status" />);

    const status = screen.getByText("started");
    expect(status).toHaveAttribute("data-variant", "running");
    expect(status).toHaveAttribute("data-size", "meta");
    expect(status).toHaveClass("run-card__status");
  });
});
