import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionTimeline } from "./SessionTimeline";

const EMPTY_DIFF_TEXT = "No diff content was provided for this operation.";

describe("SessionTimeline", () => {
  beforeEach(() => {
    vi.useRealTimers();
    HTMLElement.prototype.scrollTo = vi.fn();
  });

  it("shows the welcome screen for connected live sessions with no events yet", () => {
    render(
      <SessionTimeline
        items={[]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={0}
      />,
    );

    expect(screen.getByText("Live session")).toBeInTheDocument();
    expect(screen.getByText("Send any prompt to begin")).toBeInTheDocument();
  });

  it("preserves user-authored line breaks in message text", () => {
    const content =
      "/plan\n# Task\nadd shell command from UI\n\n## Goal\nPossibility to can run any shell command from UI using ! (e.g. !ls), use bash_tool in backend";

    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content,
            markdown: false,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    const userText = document.querySelector(".timeline-entry__user-text");
    expect(userText).not.toBeNull();
    expect(userText).toHaveClass("timeline-entry__user-text");
    expect(userText?.textContent).toBe(content);
    expect(userText?.textContent).toContain("/plan\n# Task\nadd shell command from UI");
  });

  it("still highlights file paths inside formatted user text", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Please inspect\nwebapp/src/App.tsx",
            filePaths: ["webapp/src/App.tsx"],
            markdown: false,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    expect(screen.getByText("webapp/src/App.tsx")).toHaveClass(
      "timeline-entry__file-tag",
    );
    expect(screen.getByText(/Please inspect/)).toHaveClass(
      "timeline-entry__user-text",
    );
  });

  it("keeps assistant markdown rendering separate from user text formatting", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "assistant-1",
            role: "assistant",
            content: "# Done",
            markdown: true,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Done" })).toBeInTheDocument();
    expect(screen.queryByText("# Done")).not.toBeInTheDocument();
  });

  it("renders assistant markdown tables as table elements", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "assistant-1",
            role: "assistant",
            content: [
              "| System | Patch format | Fuzzy matching |",
              "| --- | --- | --- |",
              "| pbi-agent | V4A diff | No |",
              "| Codex | apply_patch envelope | Yes |",
            ].join("\n"),
            markdown: true,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "System" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "pbi-agent" })).toBeInTheDocument();
    expect(screen.queryByText(/\| System \| Patch format/)).not.toBeInTheDocument();
  });

  it("renders apply_patch tool results as a structured git diff", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "apply_patch",
            items: [
              {
                text: "update_file TODO.md  done\ndiff:\n-[ ] Old\n+[X] New",
                classes: "tool-call-apply-patch",
                metadata: {
                  tool_name: "apply_patch",
                  path: "TODO.md",
                  operation: "update_file",
                  success: true,
                  diff: "-[ ] Old\n+[X] New",
                  call_id: "call_patch_1",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    expect(screen.getByText("TODO.md")).toBeInTheDocument();
    expect(screen.getByText("Updated")).toBeInTheDocument();
    expect(screen.getByText(/Old/).closest("code")?.textContent).toBe("[ ] Old");
    expect(screen.getByText(/New/).closest("code")?.textContent).toBe("[X] New");
    expect(screen.getByText("call_patch_1")).toBeInTheDocument();
    expect(screen.queryByText(/update_file TODO.md/)).not.toBeInTheDocument();
  });

  it("renders real apply_patch diff line numbers from metadata", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "apply_patch",
            items: [
              {
                text: "update_file src/config.ts done",
                classes: "tool-call-apply-patch",
                metadata: {
                  tool_name: "apply_patch",
                  path: "src/config.ts",
                  operation: "update_file",
                  success: true,
                  diff: " before\n-old value\n+new value\n after",
                  diff_line_numbers: [
                    { old: 41, new: 41 },
                    { old: 42, new: null },
                    { old: null, new: 42 },
                    { old: 43, new: 43 },
                  ],
                  call_id: "call_patch_numbers",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    const rows = Array.from(document.querySelectorAll(".git-diff-result__line"));
    expect(rows.map((row) => row.textContent)).toEqual([
      "4141before",
      "42-old value",
      "42+new value",
      "4343after",
    ]);
  });

  it("renders successful apply_patch delete results as a compact deleted filename", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "apply_patch",
            items: [
              {
                text: "delete_file TODO.md done",
                classes: "tool-call-apply-patch",
                metadata: {
                  tool_name: "apply_patch",
                  path: "TODO.md",
                  operation: "delete_file",
                  success: true,
                  diff: "",
                  call_id: "call_patch_delete",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Working/ }));

    const title = screen.getByText("TODO.md");
    const card = title.closest(".git-diff-result");

    expect(title).toHaveClass("git-diff-result__title--deleted");
    expect(card).toHaveAttribute("data-operation", "delete_file");
    expect(card).toHaveClass("git-diff-result--delete");
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.queryByText("Deleted")).not.toBeInTheDocument();
    expect(screen.queryByText(EMPTY_DIFF_TEXT)).not.toBeInTheDocument();
    expect(screen.queryByText("call_patch_delete")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Diff summary")).not.toBeInTheDocument();
  });

  it("highlights only the edited span for paired apply_patch replacements", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "apply_patch",
            items: [
              {
                text: "update_file src/config.ts done",
                classes: "tool-call-apply-patch",
                metadata: {
                  tool_name: "apply_patch",
                  path: "src/config.ts",
                  operation: "update_file",
                  success: true,
                  diff: " const timeout = options.timeout ?? 30000;\n-const retries = oldValue;\n+const retries = newValue;\n return timeout;",
                  call_id: "call_patch_2",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    expect(screen.getByText("1 focused change")).toBeInTheDocument();
    expect(screen.getByText("old")).toHaveClass("git-diff-result__token--removed");
    expect(screen.getByText("new")).toHaveClass("git-diff-result__token--added");
    expect(screen.getByText(/const timeout/)).not.toHaveClass(
      "git-diff-result__token--added",
    );
  });

  it("renders shell tool output as a structured terminal card", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-shell",
            label: "shell",
            items: [
              {
                text: "shell echo hello done",
                metadata: {
                  tool_name: "shell",
                  call_id: "call_shell_1",
                  status: "completed",
                  success: true,
                  arguments: { command: "echo hello", working_directory: "." },
                  result: { stdout: "hello\n", stderr: "", exit_code: 0 },
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Working/ }));

    expect(screen.getByText("echo hello")).toBeInTheDocument();
    expect(screen.getByText("Stdout")).toBeInTheDocument();
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("call_shell_1")).toBeInTheDocument();
  });

  it("renders read_file tool output as a file preview card", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-read-file",
            label: "read_file",
            items: [
              {
                text: "read_file TODO.md done",
                metadata: {
                  tool_name: "read_file",
                  status: "completed",
                  success: true,
                  arguments: { path: "TODO.md" },
                  result: {
                    path: "TODO.md",
                    start_line: 1,
                    end_line: 2,
                    total_lines: 2,
                    content: "# TODO\n[X] Done",
                  },
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Working/ }));

    expect(screen.getByText("TODO.md")).toBeInTheDocument();
    expect(screen.getByText("lines 1-2 of 2")).toBeInTheDocument();
    expect(screen.getByText(/\[X\] Done/)).toBeInTheDocument();
  });

  it("renders read_image, read_web_url, web_search, sub_agent, and generic tool cards", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-mixed",
            label: "Tool calls",
            items: [
              {
                text: "read_image logo.jpg done",
                metadata: {
                  tool_name: "read_image",
                  status: "completed",
                  success: true,
                  result: { path: "logo.jpg", mime_type: "image/jpeg", byte_count: 2048 },
                },
              },
              {
                text: "read_web_url https://example.com done",
                metadata: {
                  tool_name: "read_web_url",
                  status: "completed",
                  success: true,
                  result: { url: "https://example.com", markdown: "# Example" },
                },
              },
              {
                text: "web_search done",
                metadata: {
                  tool_name: "web_search",
                  status: "completed",
                  success: true,
                  result: {
                    queries: ["pbi-agent"],
                    sources: [{ title: "Docs", url: "https://example.com/docs", snippet: "Reference" }],
                  },
                },
              },
              {
                text: "sub_agent done",
                metadata: {
                  tool_name: "sub_agent",
                  status: "completed",
                  success: true,
                  arguments: { task_instruction: "Review tests", agent_type: "default" },
                  result: { output: "Looks good" },
                },
              },
              {
                text: "custom_tool done",
                metadata: {
                  tool_name: "mcp__custom__lookup",
                  status: "completed",
                  success: true,
                  arguments: { id: 1 },
                  result: { value: "ok" },
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Working/ }));

    expect(screen.getByText("logo.jpg")).toBeInTheDocument();
    expect(screen.getByText(/2.0 KB/)).toBeInTheDocument();
    expect(screen.getByText("https://example.com")).toBeInTheDocument();
    expect(screen.getByText("# Example")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Docs" })).toHaveAttribute("href", "https://example.com/docs");
    expect(screen.getByText("Review tests")).toBeInTheDocument();
    expect(screen.getByText("Looks good")).toBeInTheDocument();
    expect(screen.getAllByText("mcp__custom__lookup").length).toBeGreaterThan(0);
    expect(screen.getByText(/"value": "ok"/)).toBeInTheDocument();
  });

  it("pairs equal-count multi-line replacements for intraline highlights", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "apply_patch",
            items: [
              {
                text: "update_file webapp/src/styles/session.css done",
                classes: "tool-call-apply-patch",
                metadata: {
                  tool_name: "apply_patch",
                  path: "webapp/src/styles/session.css",
                  operation: "update_file",
                  success: true,
                  diff: "-.panel { padding: 48px; }\n-.panel { gap: var(--sp-5); }\n+.panel { padding: 32px; }\n+.panel { gap: var(--sp-4); }",
                  call_id: "call_patch_multi",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    expect(screen.getByText("1 focused change")).toBeInTheDocument();
    expect(screen.getByText("48")).toHaveClass("git-diff-result__token--removed");
    expect(screen.getByText("32")).toHaveClass("git-diff-result__token--added");
    expect(screen.getByText("5")).toHaveClass("git-diff-result__token--removed");
    expect(screen.getByText("4")).toHaveClass("git-diff-result__token--added");
    expect(screen.getByText("48").closest("tr")?.nextElementSibling).toBe(
      screen.getByText("32").closest("tr"),
    );
    expect(screen.getByText("5").closest("tr")?.nextElementSibling).toBe(
      screen.getByText("4").closest("tr"),
    );
  });

  it("does not pair ambiguous multi-line delete and insert blocks", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "apply_patch",
            items: [
              {
                text: "update_file src/config.ts done",
                classes: "tool-call-apply-patch",
                metadata: {
                  tool_name: "apply_patch",
                  path: "src/config.ts",
                  operation: "update_file",
                  success: true,
                  diff: "-const first = oldValue;\n-const second = oldOther;\n+const inserted = newValue;",
                  call_id: "call_patch_ambiguous",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    expect(screen.getByText(/const first/).closest("tr")).not.toHaveAttribute(
      "data-focused",
    );
    expect(screen.getByText(/const inserted/).closest("tr")).not.toHaveAttribute(
      "data-focused",
    );
    expect(screen.queryByText("old")).not.toBeInTheDocument();
    expect(screen.queryByText("new")).not.toBeInTheDocument();
  });

  it("collapses large unchanged context in apply_patch diffs", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "apply_patch",
            items: [
              {
                text: "update_file README.md done",
                classes: "tool-call-apply-patch",
                metadata: {
                  tool_name: "apply_patch",
                  path: "README.md",
                  operation: "update_file",
                  success: true,
                  diff: Array.from({ length: 8 }, (_, index) => ` line ${index + 1}`).join("\n"),
                  call_id: "call_patch_3",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    expect(screen.getByText("2 unchanged lines")).toBeInTheDocument();
  });

  it("labels failed apply_patch cards without implying the update succeeded", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "apply_patch",
            items: [
              {
                text: "update_file TODO.md failed",
                classes: "tool-call-apply-patch",
                metadata: {
                  tool_name: "apply_patch",
                  path: "TODO.md",
                  operation: "update_file",
                  success: false,
                  detail: "Invalid context",
                  diff: "-old\n+new",
                  call_id: "call_patch_4",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    expect(screen.getByText("Update failed")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.queryByText("Updated")).not.toBeInTheDocument();
  });

  it("keeps the Working badge spinner visible while the session is active", () => {
    const { rerender } = render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Do the task",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "thinking-1",
            title: "Thinking",
            content: "Planning the work",
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "model_wait", message: "Analyzing..." }}
        itemsVersion={1}
      />,
    );

    expect(screen.getByRole("button", { name: /Working/ })).toBeInTheDocument();
    expect(screen.getByLabelText("running")).toBeInTheDocument();

    rerender(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Do the task",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "thinking-1",
            title: "Thinking",
            content: "Planning the work",
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={2}
      />,
    );

    expect(screen.queryByLabelText("running")).not.toBeInTheDocument();
  });

  it("keeps following updates after programmatically scrolling to the first apply_patch diff", async () => {
    vi.useFakeTimers();

    const firstItems = [
      {
        kind: "message" as const,
        itemId: "assistant-1",
        role: "assistant" as const,
        content: "I will patch the file.",
        markdown: false,
      },
    ];

    const diffItems = [
      ...firstItems,
      {
        kind: "tool_group" as const,
        itemId: "tool-1",
        label: "apply_patch",
        status: "completed" as const,
        items: [
          {
            text: "update_file TODO.md done",
            classes: "tool-call-apply-patch",
            metadata: {
              tool_name: "apply_patch" as const,
              path: "TODO.md",
              operation: "update_file",
              success: true,
              diff: "-[ ] Old\n+[X] New",
              call_id: "call_patch_scroll",
            },
          },
        ],
      },
    ];

    const { container, rerender } = render(
      <SessionTimeline
        items={firstItems}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    const scrollArea = container.querySelector<HTMLElement>(".session-scroll-area");
    expect(scrollArea).not.toBeNull();
    Object.defineProperties(scrollArea, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1200 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });

    rerender(
      <SessionTimeline
        items={diffItems}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={2}
      />,
    );

    expect(screen.getByText("TODO.md")).toBeInTheDocument();

    fireEvent.scroll(scrollArea!);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(150);
    });

    rerender(
      <SessionTimeline
        items={diffItems}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Still working..." }}
        itemsVersion={3}
      />,
    );

    const scrollCalls = vi.mocked(HTMLElement.prototype).scrollTo.mock.calls;
    expect(scrollCalls.at(-1)?.[0]).toMatchObject({
      top: 1200,
      behavior: "instant",
    });
    expect(screen.queryByText("New messages below")).not.toBeInTheDocument();
  });

  it("color-codes the active Working header for tool_execution phase", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "shell",
            status: "running",
            items: [{ text: "ls" }],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={1}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Working/ });
    expect(trigger).toHaveAttribute("data-phase", "tool_execution");
    expect(screen.getByLabelText("running")).toBeInTheDocument();
  });

  it("color-codes the active Working header for model_wait phase", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "thinking",
            itemId: "thinking-1",
            title: "Thinking",
            content: "Planning",
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "model_wait", message: "Analyzing..." }}
        itemsVersion={1}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Working/ });
    expect(trigger).toHaveAttribute("data-phase", "model_wait");
    expect(screen.getByLabelText("running")).toBeInTheDocument();
  });

  it("renders a synthetic Working header when the latest item is a user message and the session is active", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Do the task",
            markdown: false,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "starting", message: "Starting..." }}
        itemsVersion={1}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Working/ });
    expect(trigger).toHaveAttribute("data-phase", "starting");
    expect(screen.getByLabelText("running")).toBeInTheDocument();
    // Clicking the synthetic header must not crash even with no body content.
    fireEvent.click(trigger);
    expect(screen.getByRole("button", { name: /Working/ })).toBeInTheDocument();
  });

  it("falls back to data-phase=active when waitMessage is set without processing", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Do the task",
            markdown: false,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage="Waiting for tool..."
        processing={null}
        itemsVersion={1}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Working/ });
    expect(trigger).toHaveAttribute("data-phase", "active");
    expect(screen.getByLabelText("running")).toBeInTheDocument();
  });

  it("does not render the legacy bottom processing indicator", () => {
    const { container } = render(
      <SessionTimeline
        items={[
          {
            kind: "thinking",
            itemId: "thinking-1",
            title: "Thinking",
            content: "Planning",
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "model_wait", message: "Analyzing..." }}
        itemsVersion={1}
      />,
    );

    expect(container.querySelector(".processing-indicator")).toBeNull();
    expect(screen.queryByText("Analyzing...")).not.toBeInTheDocument();
  });
});
