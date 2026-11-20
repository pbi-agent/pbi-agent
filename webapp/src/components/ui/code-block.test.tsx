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

    const wrapper = container.querySelector("[data-code-block=\"highlighted\"]");
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

  it("highlights and scrolls to a line range in plain text", () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    const { container } = render(
      <CodeBlock value={"one\ntwo\nthree\nfour"} path="notes.unknownext" highlightLines={{ start: 2, end: 3 }} />,
    );

    const pre = container.querySelector("pre")!;
    expect(pre.textContent).toBe("one\ntwo\nthree\nfour");
    const highlighted = [...container.querySelectorAll("[data-line-highlight]")].map((line) => line.textContent);
    expect(highlighted).toEqual(["two", "three"]);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(scrollIntoView.mock.contexts[0]).toHaveProperty("textContent", "two");
  });

  it("re-applies the line range once highlighted markup arrives", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    highlightCodeMock.mockResolvedValue(
      '<pre class="shiki"><code><span class="line">a</span>\n<span class="line">b</span></code></pre>',
    );
    const { container } = render(
      <CodeBlock value={"a\nb"} path="main.py" highlightLines={{ start: 9, end: 9 }} />,
    );

    await waitFor(() => expect(container.querySelector("[data-highlighted='true']")).not.toBeNull());
    const highlighted = [...container.querySelectorAll("[data-line-highlight]")].map((line) => line.textContent);
    // Out-of-range targets scroll to the last line without highlighting anything.
    expect(highlighted).toEqual([]);
    expect(scrollIntoView.mock.contexts.at(-1)).toHaveProperty("textContent", "b");
  });
});
