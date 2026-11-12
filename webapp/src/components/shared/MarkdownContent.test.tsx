import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { MarkdownContent } from "./MarkdownContent";
import { useTerminalStore } from "../terminal/terminalStore";

describe("MarkdownContent run-in-terminal", () => {
  beforeEach(() => {
    useTerminalStore.setState({ open: false, terminalId: null, pendingRun: null });
  });

  it("offers Run on bash snippets and queues the command", () => {
    render(<MarkdownContent copyable content={"```bash\nuv run ruff check .\n```"} />);
    fireEvent.click(screen.getByRole("button", { name: "Run snippet in terminal" }));
    const state = useTerminalStore.getState();
    expect(state.open).toBe(true);
    expect(state.pendingRun?.command).toBe("uv run ruff check .");
  });

  it("does not offer Run on non-shell snippets", () => {
    render(<MarkdownContent copyable content={"```python\nprint(1)\n```"} />);
    expect(screen.queryByRole("button", { name: "Run snippet in terminal" })).toBeNull();
  });
});
