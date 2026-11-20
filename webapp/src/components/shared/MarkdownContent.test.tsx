import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { MarkdownContent } from "./MarkdownContent";
import { useTerminalStore } from "../terminal/terminalStore";

describe("MarkdownContent links", () => {
  it.each(["https://markdown.new/", "http://example.com/", "//example.com/"])(
    "opens %s in a new tab",
    (url) => {
      render(<MarkdownContent content={`[Website](${url})`} />);
      const link = screen.getByRole("link", { name: "Website" });
      expect(link).toHaveAttribute("href", url);
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    },
  );

  it.each(["#section", "docs/cli.md", "mailto:help@example.com"])(
    "preserves default navigation for %s",
    (url) => {
      render(<MarkdownContent content={`[Reference](${url})`} />);
      const link = screen.getByRole("link", { name: "Reference" });
      expect(link).toHaveAttribute("href", url);
      expect(link).not.toHaveAttribute("target");
    },
  );
});

describe("MarkdownContent file-with-line links", () => {
  it.each(["README.md:42", "app.ts:3:7", "app.ts:3-9#top"])("keeps %s", (url) => {
    render(<MarkdownContent content={`[File](${url})`} />);
    expect(screen.getByText("File").closest("a")).toHaveAttribute("href", url);
  });

  it.each(["javascript:1", "data:1", "vbscript:1", "readme:42", "foo.md:bar"])(
    "still sanitizes %s",
    (url) => {
      render(<MarkdownContent content={`[File](${url})`} />);
      expect(screen.getByText("File").closest("a")).toHaveAttribute("href", "");
    },
  );
});

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
