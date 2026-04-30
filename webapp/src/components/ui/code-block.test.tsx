import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { highlightCodeMock } = vi.hoisted(() => ({
  highlightCodeMock:
    vi.fn<(code: string, language: string) => Promise<string | null>>(),
}));

vi.mock("@/lib/shiki-highlighter", () => ({
  highlightCode: highlightCodeMock,
}));

import { CodeBlock } from "./code-block";

describe("CodeBlock", () => {
  beforeEach(() => {
    highlightCodeMock.mockReset();
  });

  afterEach(() => {
    highlightCodeMock.mockReset();
  });

  it("renders plain text without invoking the highlighter when no language is known", () => {
    render(<CodeBlock value="hello world" path="notes.unknownext" />);

    expect(screen.getByText("hello world")).toBeInTheDocument();
    const pre = screen.getByText("hello world");
    expect(pre.tagName).toBe("PRE");
    expect(pre.dataset.highlighted).toBe("false");
    expect(highlightCodeMock).not.toHaveBeenCalled();
  });

  it("upgrades to highlighted markup once the highlighter resolves", async () => {
    highlightCodeMock.mockResolvedValue(
      '<pre class="shiki shiki-themes"><code><span class="line">print("hi")</span></code></pre>',
    );

    const { container } = render(
      <CodeBlock value='print("hi")' path="main.py" />,
    );

    expect(highlightCodeMock).toHaveBeenCalledWith('print("hi")', "python");

    await waitFor(() => {
      expect(container.querySelector(".shiki")).not.toBeNull();
    });

    const wrapper = container.querySelector(".tool-result__code");
    expect(wrapper).not.toBeNull();
    expect(wrapper?.getAttribute("data-language")).toBe("python");
    expect(wrapper?.getAttribute("data-highlighted")).toBe("true");
  });

  it("prefers an explicit language over the path-derived one", async () => {
    highlightCodeMock.mockResolvedValue(
      '<pre class="shiki"><code>md</code></pre>',
    );

    render(<CodeBlock value="# heading" path="data.json" language="markdown" />);

    await waitFor(() => {
      expect(highlightCodeMock).toHaveBeenCalledWith("# heading", "markdown");
    });
  });

  it("keeps the plain text fallback when highlighting returns null", async () => {
    highlightCodeMock.mockResolvedValue(null);

    render(<CodeBlock value="snippet" path="main.py" />);

    await waitFor(() => {
      expect(highlightCodeMock).toHaveBeenCalled();
    });

    const pre = screen.getByText("snippet");
    expect(pre.tagName).toBe("PRE");
    expect(pre.dataset.highlighted).toBe("false");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
