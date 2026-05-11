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
});
