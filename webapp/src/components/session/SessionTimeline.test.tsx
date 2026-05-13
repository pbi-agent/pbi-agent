import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../ui/tooltip";
import { SessionTimeline } from "./SessionTimeline";

const EMPTY_DIFF_TEXT = "No diff content was provided for this operation.";

const navigateMock = vi.hoisted(() => vi.fn());

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

function openWorking(index = 0, expandInner = true) {
  const workingButton = screen.getAllByRole("button", { name: /Working/ })[index];
  fireEvent.click(workingButton);
  if (expandInner) {
    for (const groupButton of screen.queryAllByRole("button", { name: /^Thinking$/i })) {
      fireEvent.click(groupButton);
    }
    for (const toolButton of screen.queryAllByRole("button").filter((button) =>
      button.classList.contains("working-items__tool-trigger"),
    )) {
      fireEvent.click(toolButton);
    }
  }
  return workingButton;
}

describe("SessionTimeline", () => {
  beforeEach(() => {
    vi.useRealTimers();
    HTMLElement.prototype.scrollTo = vi.fn();
    navigateMock.mockReset();
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

    expect(screen.getByText(/work smart/i)).toBeInTheDocument();
    expect(screen.getByText("Send any prompt to begin")).toBeInTheDocument();
  });

  it("hides generic retry notice and error messages while preserving other timeline messages", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "retry-notice",
            role: "notice",
            content: "Retrying... (1/3)",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "retry-error",
            role: "error",
            content: "  Retrying... (2/3)  ",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "rate-limit",
            role: "notice",
            content: "Rate limit reached. Retrying in 5s...",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "overloaded",
            role: "notice",
            content: "Provider overloaded. Retrying in 10s...",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "real-error",
            role: "error",
            content: "Request failed after retries",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "assistant-retry-text",
            role: "assistant",
            content: "Retrying... (3/3)",
            markdown: false,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={6}
      />,
    );

    expect(screen.queryByText("Retrying... (1/3)")).not.toBeInTheDocument();
    expect(screen.queryByText("Retrying... (2/3)")).not.toBeInTheDocument();
    expect(screen.getByText("Rate limit reached. Retrying in 5s...")).toBeInTheDocument();
    expect(screen.getByText("Provider overloaded. Retrying in 10s...")).toBeInTheDocument();
    expect(screen.getByText("Request failed after retries")).toBeInTheDocument();
    expect(screen.getByText("Retrying... (3/3)")).toBeInTheDocument();
  });

  it("keeps active Working anchored after the latest visible message when a hidden retry arrives", () => {
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
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "starting", message: "Starting..." }}
        itemsVersion={1}
      />,
    );

    const workingButton = screen.getByRole("button", { name: "Working" });

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
            kind: "message",
            itemId: "retry-1",
            role: "error",
            content: "Retrying... (1/3)",
            markdown: false,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "starting", message: "Starting..." }}
        itemsVersion={2}
      />,
    );

    expect(screen.queryByText("Retrying... (1/3)")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Working" })).toBe(workingButton);
  });

  it("renders a stable startup Working placeholder before first activity", () => {
    render(
      <SessionTimeline
        items={[]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "starting", message: "Starting..." }}
        itemsVersion={0}
      />,
    );

    const trigger = screen.getByRole("button", { name: "Working" });
    expect(trigger).toHaveAttribute("data-phase", "starting");
    expect(trigger).toHaveTextContent("WorkingPreparing…");
    expect(screen.queryByText(/work smart/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Thinking$/i })).not.toBeInTheDocument();
  });

  it("reuses the startup Working block when slow first unanchored activity arrives", () => {
    const { rerender } = render(
      <SessionTimeline
        items={[]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "model_wait", message: "Thinking..." }}
        itemsVersion={0}
      />,
    );

    const trigger = screen.getByRole("button", { name: "Working" });

    rerender(
      <SessionTimeline
        items={[
          {
            kind: "tool_group" as const,
            itemId: "tool-1",
            label: "shell",
            status: "running" as const,
            items: [
              {
                text: "pwd",
                metadata: {
                  tool_name: "shell",
                  status: "running" as const,
                  command: "pwd",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={1}
      />,
    );

    const updatedTrigger = screen.getByRole("button", { name: "Working 1 shell" });
    expect(updatedTrigger).toBe(trigger);
    expect(updatedTrigger).toHaveTextContent("Working1 shell");
    expect(screen.queryByText("Preparing…")).not.toBeInTheDocument();
  });

  it("renders first fast activity with counts instead of the startup placeholder", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group" as const,
            itemId: "tool-1",
            label: "shell",
            status: "running" as const,
            items: [
              {
                text: "pwd",
                metadata: {
                  tool_name: "shell",
                  status: "running" as const,
                  command: "pwd",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={1}
      />,
    );

    const trigger = screen.getByRole("button", { name: "Working 1 shell" });
    expect(trigger).toHaveTextContent("Working1 shell");
    expect(screen.queryByText("Preparing…")).not.toBeInTheDocument();
  });

  it("reuses the user-anchored Working block when slow first activity arrives", () => {
    const { rerender } = render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Run it",
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

    const trigger = screen.getByRole("button", { name: "Working" });

    rerender(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Run it",
            markdown: false,
          },
          {
            kind: "tool_group" as const,
            itemId: "tool-1",
            label: "shell",
            status: "running" as const,
            items: [
              {
                text: "pwd",
                metadata: {
                  tool_name: "shell",
                  status: "running" as const,
                  command: "pwd",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={2}
      />,
    );

    expect(screen.getByRole("button", { name: "Working 1 shell" })).toBe(trigger);
  });

  it("coalesces interleaved sub-agent work into one turn-level Working block", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Research this",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "think-a",
            title: "Thinking",
            content: "Researcher plan",
            subAgentId: "subagent-a",
          },
          {
            kind: "tool_group",
            itemId: "tool-b",
            label: "read_file",
            status: "completed",
            subAgentId: "subagent-b",
            items: [{ text: "Designer inspected layout" }],
          },
          {
            kind: "thinking",
            itemId: "think-a-2",
            title: "Thinking",
            content: "Researcher synthesis",
            subAgentId: "subagent-a",
          },
          {
            kind: "tool_group",
            itemId: "tool-c",
            label: "shell",
            status: "completed",
            subAgentId: "subagent-c",
            items: [{ text: "Tester verified behavior" }],
          },
          {
            kind: "message",
            itemId: "assistant-1",
            role: "assistant",
            content: "Done",
            markdown: true,
          },
        ]}
        subAgents={{
          "subagent-a": { title: "Researcher", status: "completed" },
          "subagent-b": { title: "Designer", status: "completed" },
          "subagent-c": { title: "Tester", status: "completed" },
        }}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    const workingButtons = screen.getAllByRole("button", { name: /Working/ });
    expect(workingButtons).toHaveLength(1);
    expect(workingButtons[0]).toHaveAccessibleName("Working 3 agents");
    expect(workingButtons[0]).toHaveTextContent(/^Working3 agents$/);

    openWorking(0, false);

    expect(screen.getAllByText("Researcher")).toHaveLength(1);
    expect(screen.getByText("Designer")).toBeInTheDocument();
    expect(screen.getByText("Tester")).toBeInTheDocument();
    expect(screen.queryByText("Researcher plan")).not.toBeInTheDocument();
    expect(screen.queryByText("Designer inspected layout")).not.toBeInTheDocument();

    const first = screen.getByText("Researcher");
    const second = screen.getByText("Designer");
    const third = screen.getByText("Tester");
    expect(first.compareDocumentPosition(second)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(second.compareDocumentPosition(third)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("keeps the main Working label shimmering while a collapsed sub-agent is running", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Research this",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "subagent-a-card",
            title: "Sub-agent",
            content: "",
            subAgentId: "subagent-a",
          },
        ]}
        subAgents={{
          "subagent-a": { title: "Researcher", status: "running" },
        }}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    const workingButton = screen.getByRole("button", { name: "Working 1 agent" });
    expect(workingButton.querySelector('[data-component="text-shimmer"]')).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  it("renders thinking and tool rows directly inside an expanded Working group", () => {
    const { container } = render(
      <SessionTimeline
        items={[
          {
            kind: "thinking",
            itemId: "think-1",
            title: "Thinking",
            content: "Planning the next steps",
          },
          {
            kind: "tool_group",
            itemId: "tools-1",
            label: "Tools",
            status: "completed",
            items: [
              {
                text: "file contents",
                metadata: { tool_name: "read_file", arguments: { path: "README.md" }, result: { path: "README.md", content: "file contents" } },
              },
              {
                text: "command output",
                metadata: { tool_name: "shell", command: "bun run typecheck", result: { stdout: "ok", stderr: "", exit_code: 0 } },
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

    expect(screen.getByRole("button", { name: /Working.*1 thought, 1 read, 1 shell/i })).toBeInTheDocument();
    const workingSummary = container.querySelector(".timeline-entry__header--work-run .working-items__summary");
    expect(workingSummary).toHaveTextContent("1 thought, 1 read, 1 shell");
    expect(workingSummary?.querySelectorAll('[data-component="animated-number"]')).toHaveLength(3);
    expect(workingSummary?.querySelector('[data-slot="animated-number-strip"]')).toBeInTheDocument();

    openWorking(0, false);
    expect(screen.getByRole("button", { name: /^Thinking$/i })).toBeInTheDocument();
    expect(screen.queryByText(/thinking block/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Read.*README.md/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Command.*bun run typecheck/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Activity/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /In motion/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /read_file/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /shell.*bun run typecheck/i })).not.toBeInTheDocument();
    expect(screen.queryByText("file contents")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Read.*README.md/i }));
    expect(screen.getByText("file contents")).toBeInTheDocument();
    expect(screen.queryByText("ok")).not.toBeInTheDocument();
  });

  it("shows long Working tool lists in a five-row scroll area and centers opened tools", async () => {
    const scrollTo = vi.fn();
    HTMLElement.prototype.scrollTo = scrollTo;
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 0;
    });
    const { container } = render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tools-1",
            label: "Tools",
            status: "completed",
            items: Array.from({ length: 7 }, (_, index) => ({
              text: `file ${index + 1}`,
              metadata: {
                tool_name: "read_file",
                arguments: { path: `file-${index + 1}.txt` },
                result: { path: `file-${index + 1}.txt`, content: `file ${index + 1}` },
              },
            })),
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    openWorking(0, false);
    const scrollArea = container.querySelector<HTMLElement>(".working-items--scrollable");
    expect(scrollArea).toBeInTheDocument();
    if (!scrollArea) throw new Error("Expected scrollable Working items area");
    expect(screen.getAllByRole("button").filter((button) =>
      button.classList.contains("working-items__tool-trigger"),
    )).toHaveLength(7);

    Object.defineProperty(scrollArea, "clientHeight", { configurable: true, value: 200 });
    Object.defineProperty(scrollArea, "scrollHeight", { configurable: true, value: 600 });
    scrollArea.scrollTop = 100;
    scrollArea.getBoundingClientRect = () => ({
      x: 0,
      y: 0,
      top: 0,
      right: 300,
      bottom: 200,
      left: 0,
      width: 300,
      height: 200,
      toJSON: () => ({}),
    });

    const sixthToolButton = screen.getByRole("button", { name: /Read.*file-6\.txt/i });
    const sixthToolItem = sixthToolButton.closest<HTMLElement>(".working-items__item");
    expect(sixthToolItem).not.toBeNull();
    sixthToolItem!.getBoundingClientRect = () => ({
      x: 0,
      y: 300,
      top: 300,
      right: 300,
      bottom: 340,
      left: 0,
      width: 300,
      height: 40,
      toJSON: () => ({}),
    });

    fireEvent.click(sixthToolButton);

    await waitFor(() => {
      expect(scrollTo).toHaveBeenCalledWith({
        top: 320,
        behavior: "smooth",
      });
    });
    rafSpy.mockRestore();
  });

  it("grows the long Working scroll area enough to fit an opened tool card", async () => {
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 0;
    });
    const { container } = render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tools-1",
            label: "Tools",
            status: "completed",
            items: Array.from({ length: 7 }, (_, index) => ({
              text: `file ${index + 1}`,
              metadata: {
                tool_name: "read_file",
                arguments: { path: `file-${index + 1}.txt` },
                result: { path: `file-${index + 1}.txt`, content: `file ${index + 1}` },
              },
            })),
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    openWorking(0, false);
    const scrollArea = container.querySelector<HTMLElement>(".working-items--scrollable");
    expect(scrollArea).toBeInTheDocument();
    if (!scrollArea) throw new Error("Expected scrollable Working items area");
    Object.defineProperty(scrollArea, "clientHeight", { configurable: true, value: 160 });
    Object.defineProperty(scrollArea, "scrollHeight", { configurable: true, value: 700 });

    const sixthToolButton = screen.getByRole("button", { name: /Read.*file-6\.txt/i });
    const sixthToolItem = sixthToolButton.closest<HTMLElement>(".working-items__item");
    expect(sixthToolItem).not.toBeNull();
    Object.defineProperty(sixthToolItem!, "scrollHeight", { configurable: true, value: 320 });

    fireEvent.click(sixthToolButton);

    await waitFor(() => {
      expect(scrollArea.style.getPropertyValue("--working-items-max-height")).toBe("336px");
    });
    rafSpy.mockRestore();
  });

  it("offers a shortcut button to fully expand long Working tool lists", async () => {
    const { container } = render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tools-1",
            label: "Tools",
            status: "completed",
            items: Array.from({ length: 7 }, (_, index) => ({
              text: `file ${index + 1}`,
              metadata: {
                tool_name: "read_file",
                arguments: { path: `file-${index + 1}.txt` },
                result: { path: `file-${index + 1}.txt`, content: `file ${index + 1}` },
              },
            })),
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    openWorking(0, false);

    const expandButton = screen.getByRole("button", { name: "Fully expand Working tool list" });
    expect(expandButton).toHaveTextContent("+2 more");

    fireEvent.click(expandButton);

    await waitFor(() => {
      expect(container.querySelector(".working-items--fully-expanded")).toBeInTheDocument();
    });
    const limitButton = screen.getByRole("button", { name: "Limit Working tool list to five rows" });
    expect(limitButton).toHaveAttribute("aria-pressed", "true");
    expect(limitButton).toHaveTextContent("Show recent 5");
  });

  it("closes the previously opened tool card when another tool card is opened", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tools-1",
            label: "Tool calls",
            status: "completed",
            items: [
              {
                text: "read_file alpha.txt",
                metadata: {
                  tool_name: "read_file",
                  arguments: { path: "alpha.txt" },
                  result: { path: "alpha.txt", content: "ALPHA_CONTENT" },
                },
              },
              {
                text: "read_file beta.txt",
                metadata: {
                  tool_name: "read_file",
                  arguments: { path: "beta.txt" },
                  result: { path: "beta.txt", content: "BETA_CONTENT" },
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

    openWorking(0, false);
    const toolButtons = () =>
      screen.getAllByRole("button").filter((button) =>
        button.classList.contains("working-items__tool-trigger"),
      );

    fireEvent.click(toolButtons()[0]);
    expect(screen.getByText("ALPHA_CONTENT")).toBeInTheDocument();
    expect(screen.queryByText("BETA_CONTENT")).not.toBeInTheDocument();
    expect(toolButtons()[0]).toHaveAttribute("aria-expanded", "true");
    expect(toolButtons()[1]).toHaveAttribute("aria-expanded", "false");

    // Opening the second tool card must close the first one.
    fireEvent.click(toolButtons()[1]);
    expect(screen.queryByText("ALPHA_CONTENT")).not.toBeInTheDocument();
    expect(screen.getByText("BETA_CONTENT")).toBeInTheDocument();
    expect(toolButtons()[0]).toHaveAttribute("aria-expanded", "false");
    expect(toolButtons()[1]).toHaveAttribute("aria-expanded", "true");
  });

  it("summarizes read_web_url as a read in the collapsed Working header", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tools-1",
            label: "Tool calls",
            status: "completed",
            items: [
              {
                text: "read_web_url https://example.com done",
                metadata: { tool_name: "read_web_url", result: { url: "https://example.com" } },
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

    const workingButton = screen.getByRole("button", { name: "Working 1 read" });
    expect(workingButton).toHaveTextContent(/^Working1 read$/);
  });

  it("summarizes built-in tools by category and falls back to tool classes/text", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "tool_group",
            itemId: "tools-1",
            label: "Tool calls",
            status: "completed",
            items: [
              { text: "read_file README.md done", metadata: { tool_name: "read_file" } },
              { text: "Fetched https://example.com", classes: "tool-call-read-web-url" },
              { text: "web_search pbi-agent done", metadata: { tool_name: "web_search" } },
              { text: "shell bun run typecheck done", metadata: { tool_name: "shell" } },
              { text: "apply_patch done", metadata: { tool_name: "apply_patch" } },
              { text: "replace_in_file done", metadata: { tool_name: "replace_in_file" } },
              { text: "write_file done", metadata: { tool_name: "write_file" } },
              { text: "sub_agent done", metadata: { tool_name: "sub_agent" } },
              { text: "ask_user done", metadata: { tool_name: "ask_user" } },
              { text: "mcp__custom__lookup done", metadata: { tool_name: "mcp__custom__lookup" } },
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

    expect(screen.getByRole("button", {
      name: "Working 2 reads, 1 search, 1 shell, 3 edits, 1 agent, 1 question, 1 other",
    })).toBeInTheDocument();
  });

  it("summarizes thoughts and sub-agent calls in the collapsed Working header without showing sub-agent names", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "thinking",
            itemId: "think-1",
            title: "Thinking",
            content: "Planning",
            subAgentId: "subagent-researcher",
          },
          {
            kind: "tool_group",
            itemId: "tool-1",
            label: "read_file",
            status: "completed",
            subAgentId: "subagent-researcher",
            items: [{ text: "Read notes" }],
          },
        ]}
        subAgents={{
          "subagent-researcher": {
            title: "Researcher",
            status: "completed",
          },
        }}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    const workingButton = screen.getByRole("button", { name: /Working/ });
    expect(workingButton).toHaveAccessibleName("Working 1 agent");
    expect(workingButton).toHaveTextContent(/^Working1 agent$/);
    expect(screen.queryByText("Researcher")).not.toBeInTheDocument();
  });

  it("renders animated odometer counts when working summaries update", () => {
    const baseItems = [
      {
        kind: "tool_group" as const,
        itemId: "tools-1",
        label: "Tools",
        status: "running" as const,
        items: [
          {
            text: "first read",
            metadata: { tool_name: "read_file", arguments: { path: "README.md" } },
          },
        ],
      },
    ];
    const { container, rerender } = render(
      <SessionTimeline
        items={baseItems}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    const workingButton = screen.getByRole("button", { name: /Working 1 read/i });
    expect(workingButton).toHaveTextContent(/^Working1 read$/);
    expect(
      workingButton.querySelectorAll('[data-component="animated-number"]'),
    ).toHaveLength(1);
    expect(
      workingButton.querySelector('[data-slot="animated-number-strip"]'),
    ).toBeInTheDocument();

    rerender(
      <SessionTimeline
        items={[
          {
            ...baseItems[0],
            items: [
              ...baseItems[0].items,
              {
                text: "second read",
                metadata: { tool_name: "read_file", arguments: { path: "package.json" } },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={2}
      />,
    );

    const updatedWorkingButton = screen.getByRole("button", { name: /Working 2 reads/i });
    expect(updatedWorkingButton).toHaveTextContent(/^Working2 reads$/);
    expect(
      updatedWorkingButton.querySelector('[data-slot="animated-number-strip"]'),
    ).toHaveAttribute("data-animating", "true");
    expect(container.querySelector('[data-slot="animated-number-cell"]')).toBeInTheDocument();
  });

  it("shows only the sub-agent name in per-turn metadata headers", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "sub-message-1",
            role: "assistant",
            content: "Sub-agent answer",
            markdown: true,
            subAgentId: "subagent-dionysus",
          },
        ]}
        subAgents={{
          "subagent-dionysus": {
            title: "Dionysus · Read the workspace LICENSE file and summarize its license terms. · low",
            status: "completed",
          },
        }}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
        showSubAgentCards={false}
      />,
    );

    expect(screen.getByText("Dionysus")).toBeInTheDocument();
    expect(screen.queryByText(/Read the workspace LICENSE file/)).not.toBeInTheDocument();
    expect(screen.queryByText(/low/)).not.toBeInTheDocument();
  });

  it("opens a read-only child route from a simplified sub-agent card", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "sub-message-1",
            role: "assistant",
            content: "Hidden sub-agent transcript",
            markdown: true,
            subAgentId: "subagent-researcher",
          },
        ]}
        subAgents={{
          "subagent-researcher": {
            title: "Researcher · Read the workspace LICENSE file and summarize its license terms. · low",
            status: "completed",
          },
        }}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
        parentSessionId="parent-session"
      />,
    );

    openWorking(0, false);
    expect(screen.queryByText("Hidden sub-agent transcript")).not.toBeInTheDocument();
    expect(screen.getByText("Researcher")).toBeInTheDocument();
    expect(screen.queryByText(/Read the workspace LICENSE file/)).not.toBeInTheDocument();
    expect(screen.queryByText(/low/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Open Researcher agent session/i }));
    expect(navigateMock).toHaveBeenCalledWith(
      "/sessions/parent-session/sub-agents/subagent-researcher",
    );
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

    openWorking();

    expect(screen.getAllByText("TODO.md")[0]).toBeInTheDocument();
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

    openWorking();

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

    openWorking();

    const title = screen.getAllByText("TODO.md").find((element) =>
      element.classList.contains("git-diff-result__title--deleted"),
    );
    expect(title).toBeDefined();
    const card = title?.closest(".git-diff-result");

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

    openWorking();

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

    openWorking();

expect(screen.getAllByText("echo hello")[0]).toBeInTheDocument();
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

    openWorking();

    expect(screen.getAllByText("TODO.md")[0]).toBeInTheDocument();
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

    // Working block is a single-open accordion: only one tool card is
    // expanded at a time. Open each tool card in turn and verify its
    // content renders correctly.
    openWorking(0, false);
    const toolButtons = () =>
      screen.getAllByRole("button").filter((button) =>
        button.classList.contains("working-items__tool-trigger"),
      );

    fireEvent.click(toolButtons()[0]);
    expect(screen.getAllByText("logo.jpg")[0]).toBeInTheDocument();
    expect(screen.getByText(/2.0 KB/)).toBeInTheDocument();

    fireEvent.click(toolButtons()[1]);
    expect(screen.getAllByText("https://example.com")[0]).toBeInTheDocument();
    expect(screen.getByText("# Example")).toBeInTheDocument();

    fireEvent.click(toolButtons()[2]);
    expect(screen.getByRole("link", { name: "Docs" })).toHaveAttribute("href", "https://example.com/docs");

    fireEvent.click(toolButtons()[3]);
    expect(screen.getByText("Review tests")).toBeInTheDocument();
    expect(screen.getByText("Looks good")).toBeInTheDocument();

    fireEvent.click(toolButtons()[4]);
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

    openWorking();

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

    openWorking();

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

    openWorking();

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

    openWorking();

    expect(screen.getByText("Update failed")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.queryByText("Updated")).not.toBeInTheDocument();
  });

  it("animates the Working label while the session is active", () => {
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

    const workingButton = screen.getByRole("button", { name: /Working/ });
    expect(workingButton).toBeInTheDocument();
    expect(workingButton.querySelector('[data-component="text-shimmer"]')).toHaveAttribute("data-active", "true");
    expect(screen.queryByLabelText("running")).not.toBeInTheDocument();

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

  it("closes open work details when the final assistant response arrives", async () => {
    const itemsBeforeFinal = [
      {
        kind: "message" as const,
        itemId: "user-1",
        role: "user" as const,
        content: "Do the task",
        markdown: false,
      },
      {
        kind: "tool_group" as const,
        itemId: "tool-1",
        label: "apply_patch",
        status: "completed" as const,
        items: [
          {
            text: "update_file TODO.md done",
            metadata: {
              tool_name: "apply_patch" as const,
              path: "TODO.md",
              operation: "update_file",
              success: true,
              diff: "-[ ] Old\n+[X] New",
            },
          },
        ],
      },
    ];

    const { rerender } = render(
      <SessionTimeline
        items={itemsBeforeFinal}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
    );

    let workingButton = screen.getByRole("button", { name: /Working/ });
    expect(workingButton).toHaveAttribute("aria-expanded", "false");

    workingButton = openWorking();

    expect(workingButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("TODO.md")[0]).toBeInTheDocument();

    rerender(
      <SessionTimeline
        items={[
          ...itemsBeforeFinal,
          {
            kind: "message",
            itemId: "assistant-1",
            role: "assistant",
            content: "Done.",
            markdown: true,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={2}
      />,
    );

    await waitFor(() => {
      expect(workingButton).toHaveAttribute("aria-expanded", "false");
    });
    expect(screen.queryByText("TODO.md")).not.toBeInTheDocument();
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

    openWorking();

    expect(screen.getAllByText("TODO.md")[0]).toBeInTheDocument();

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

  it("top-aligns newly sent text-only user messages", async () => {
    const { container, rerender } = render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "assistant-1",
            role: "assistant",
            content: "Ready.",
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

    const scrollArea = container.querySelector<HTMLElement>(".session-scroll-area");
    expect(scrollArea).not.toBeNull();
    Object.defineProperties(scrollArea!, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1200 },
      scrollTop: { configurable: true, writable: true, value: 500 },
    });
    const scrollSpy = vi.spyOn(scrollArea!, "scrollTo");
    scrollSpy.mockClear();

    rerender(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "assistant-1",
            role: "assistant",
            content: "Ready.",
            markdown: false,
          },
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
        processing={null}
        itemsVersion={2}
      />,
    );

    const userEntry = container.querySelector<HTMLElement>('[data-timeline-item-id="user-1"]');
    expect(userEntry).not.toBeNull();
    Object.defineProperty(userEntry!, "offsetTop", {
      configurable: true,
      value: 650,
    });

    await waitFor(() => {
      expect(scrollSpy).toHaveBeenCalledWith({
        top: 642,
        behavior: "instant",
      });
    });
  });

  it("keeps the bottom of newly sent image user messages visible without jumping upward", async () => {
    const originalImageComplete = Object.getOwnPropertyDescriptor(
      HTMLImageElement.prototype,
      "complete",
    );
    let rectSpy: ReturnType<typeof vi.spyOn> | undefined;
    Object.defineProperty(HTMLImageElement.prototype, "complete", {
      configurable: true,
      get: () => false,
    });

    const { container, rerender } = render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "assistant-1",
            role: "assistant",
            content: "Ready.",
            markdown: false,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
      { wrapper: TooltipProvider },
    );

    const scrollArea = container.querySelector<HTMLElement>(".session-scroll-area");
    expect(scrollArea).not.toBeNull();
    Object.defineProperties(scrollArea!, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1400 },
      scrollTop: { configurable: true, writable: true, value: 600 },
    });
    const scrollSpy = vi.spyOn(scrollArea!, "scrollTo");
    scrollSpy.mockClear();

    try {
      rerender(
        <SessionTimeline
          items={[
            {
              kind: "message",
              itemId: "assistant-1",
              role: "assistant",
              content: "Ready.",
              markdown: false,
            },
            {
              kind: "message",
              itemId: "user-1",
              role: "user",
              content: "Describe this image",
              markdown: false,
              imageAttachments: [
                {
                  upload_id: "upload-1",
                  name: "tall.png",
                  mime_type: "image/png",
                  byte_count: 1234,
                  preview_url: "/uploads/upload-1/preview",
                },
              ],
            },
          ]}
          subAgents={{}}
          connection="connected"
          waitMessage={null}
          processing={null}
          itemsVersion={2}
        />,
      );

      const userEntry = container.querySelector<HTMLElement>('[data-timeline-item-id="user-1"]');
      const image = screen.getByRole("img", { name: "tall.png" });
      expect(userEntry).not.toBeNull();
      Object.defineProperty(userEntry!, "offsetTop", {
        configurable: true,
        value: 200,
      });
      rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect");
      rectSpy.mockImplementation(function getMockRect(this: HTMLElement) {
        if (this === scrollArea) {
          return {
            x: 0,
            y: 0,
            top: 0,
            right: 400,
            bottom: 400,
            left: 0,
            width: 400,
            height: 400,
            toJSON: () => ({}),
          };
        }
        if (this === userEntry) {
          return {
            x: 0,
            y: 0,
            top: 0,
            right: 400,
            bottom: 700,
            left: 0,
            width: 400,
            height: 700,
            toJSON: () => ({}),
          };
        }
        return {
          x: 0,
          y: 0,
          top: 0,
          right: 0,
          bottom: 0,
          left: 0,
          width: 0,
          height: 0,
          toJSON: () => ({}),
        };
      });

      fireEvent.load(image);

      await waitFor(() => {
        expect(scrollSpy).toHaveBeenCalledWith({
          top: 900,
          behavior: "instant",
        });
      });
      expect(scrollSpy).not.toHaveBeenCalledWith({
        top: 192,
        behavior: "instant",
      });
    } finally {
      rectSpy?.mockRestore();
      if (originalImageComplete) {
        Object.defineProperty(HTMLImageElement.prototype, "complete", originalImageComplete);
      } else {
        delete (HTMLImageElement.prototype as { complete?: boolean }).complete;
      }
    }
  });

  it("bottom-aligns image user messages that update an existing latest user item", async () => {
    const originalImageComplete = Object.getOwnPropertyDescriptor(
      HTMLImageElement.prototype,
      "complete",
    );
    let rectSpy: ReturnType<typeof vi.spyOn> | undefined;
    Object.defineProperty(HTMLImageElement.prototype, "complete", {
      configurable: true,
      get: () => false,
    });

    const { container, rerender } = render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "assistant-1",
            role: "assistant",
            content: "Ready.",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Describe this image",
            markdown: false,
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={1}
      />,
      { wrapper: TooltipProvider },
    );

    const scrollArea = container.querySelector<HTMLElement>(".session-scroll-area");
    expect(scrollArea).not.toBeNull();
    Object.defineProperties(scrollArea!, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1400 },
      scrollTop: { configurable: true, writable: true, value: 100 },
    });
    const scrollSpy = vi.spyOn(scrollArea!, "scrollTo");
    scrollSpy.mockClear();

    try {
      fireEvent.scroll(scrollArea!);

      rerender(
        <SessionTimeline
          items={[
            {
              kind: "message",
              itemId: "assistant-1",
              role: "assistant",
              content: "Ready.",
              markdown: false,
            },
            {
              kind: "message",
              itemId: "user-1",
              role: "user",
              content: "Describe this image",
              markdown: false,
              imageAttachments: [
                {
                  upload_id: "upload-1",
                  name: "tall.png",
                  mime_type: "image/png",
                  byte_count: 1234,
                  preview_url: "/uploads/upload-1/preview",
                },
              ],
            },
          ]}
          subAgents={{}}
          connection="connected"
          waitMessage={null}
          processing={null}
          itemsVersion={2}
        />,
      );

      const userEntry = container.querySelector<HTMLElement>('[data-timeline-item-id="user-1"]');
      const image = screen.getByRole("img", { name: "tall.png" });
      expect(userEntry).not.toBeNull();
      rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect");
      rectSpy.mockImplementation(function getMockRect(this: HTMLElement) {
        if (this === scrollArea) {
          return {
            x: 0,
            y: 0,
            top: 0,
            right: 400,
            bottom: 400,
            left: 0,
            width: 400,
            height: 400,
            toJSON: () => ({}),
          };
        }
        if (this === userEntry) {
          return {
            x: 0,
            y: 0,
            top: 0,
            right: 400,
            bottom: 700,
            left: 0,
            width: 400,
            height: 700,
            toJSON: () => ({}),
          };
        }
        return {
          x: 0,
          y: 0,
          top: 0,
          right: 0,
          bottom: 0,
          left: 0,
          width: 0,
          height: 0,
          toJSON: () => ({}),
        };
      });

      fireEvent.load(image);

      await waitFor(() => {
        expect(scrollSpy).toHaveBeenCalledWith({
          top: 400,
          behavior: "instant",
        });
      });
      expect(screen.queryByText("New messages below")).not.toBeInTheDocument();
    } finally {
      rectSpy?.mockRestore();
      if (originalImageComplete) {
        Object.defineProperty(HTMLImageElement.prototype, "complete", originalImageComplete);
      } else {
        delete (HTMLImageElement.prototype as { complete?: boolean }).complete;
      }
    }
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
    const shimmer = trigger.querySelector('[data-component="text-shimmer"]');
    expect(shimmer).toHaveAttribute("data-active", "true");
    expect(shimmer?.querySelector('[data-slot="text-shimmer-char-shimmer"]')).toHaveAttribute("data-run", "true");
    expect(screen.queryByLabelText("running")).not.toBeInTheDocument();
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
    const shimmer = trigger.querySelector('[data-component="text-shimmer"]');
    expect(shimmer).toHaveAttribute("data-active", "true");
    expect(shimmer?.querySelector('[data-slot="text-shimmer-char-shimmer"]')).toHaveAttribute("data-run", "true");
    expect(screen.queryByLabelText("running")).not.toBeInTheDocument();
  });

  it("delays active Working phase color changes without replacing the shimmer label", () => {
    vi.useFakeTimers();
    const items = [
      {
        kind: "thinking" as const,
        itemId: "thinking-1",
        title: "Thinking",
        content: "Planning",
      },
    ];
    const { rerender } = render(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "model_wait", message: "Analyzing..." }}
        itemsVersion={1}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Working/ });
    const shimmer = trigger.querySelector('[data-component="text-shimmer"]');
    expect(shimmer).toHaveAttribute("data-active", "true");
    expect(trigger).toHaveAttribute("data-phase", "model_wait");

    rerender(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={2}
      />,
    );

    expect(trigger).toHaveAttribute("data-phase", "model_wait");
    expect(trigger.querySelector('[data-component="text-shimmer"]')).toBe(shimmer);
    expect(screen.queryByLabelText("running")).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(900);
    });

    expect(trigger).toHaveAttribute("data-phase", "tool_execution");
    expect(trigger.querySelector('[data-component="text-shimmer"]')).toBe(shimmer);
  });

  it("keeps the active Working shimmer stable and delays color changes when the first tool run replaces the placeholder", () => {
    vi.useFakeTimers();
    const initialItems = [
      {
        kind: "message" as const,
        itemId: "user-1",
        role: "user" as const,
        content: "Do the task",
        markdown: false,
      },
    ];
    const toolItems = [
      ...initialItems,
      {
        kind: "tool_group" as const,
        itemId: "tool-1",
        label: "shell",
        status: "running" as const,
        items: [
          {
            text: "Running command",
            metadata: {
              tool_name: "shell" as const,
              command: "echo ok",
            },
          },
        ],
      },
    ];
    const { rerender } = render(
      <SessionTimeline
        items={initialItems}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "model_wait", message: "Analyzing..." }}
        itemsVersion={1}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Working/ });
    const shimmer = trigger.querySelector('[data-component="text-shimmer"]');
    expect(shimmer).toHaveAttribute("data-active", "true");
    expect(trigger).toHaveAttribute("data-phase", "model_wait");

    rerender(
      <SessionTimeline
        items={toolItems}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={2}
      />,
    );

    expect(trigger).toHaveAttribute("data-phase", "model_wait");
    expect(trigger.querySelector('[data-component="text-shimmer"]')).toBe(shimmer);
    expect(screen.queryByLabelText("running")).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(900);
    });

    expect(trigger).toHaveAttribute("data-phase", "tool_execution");
    expect(trigger.querySelector('[data-component="text-shimmer"]')).toBe(shimmer);
  });

  it("clears stale queued active Working phases when the current phase returns to the visible color", () => {
    vi.useFakeTimers();
    const items = [
      {
        kind: "thinking" as const,
        itemId: "thinking-1",
        title: "Thinking",
        content: "Planning",
      },
    ];
    const { rerender } = render(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "model_wait", message: "Analyzing..." }}
        itemsVersion={1}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Working/ });
    expect(trigger).toHaveAttribute("data-phase", "model_wait");

    rerender(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={2}
      />,
    );
    rerender(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "model_wait", message: "Analyzing..." }}
        itemsVersion={3}
      />,
    );

    expect(trigger).toHaveAttribute("data-phase", "model_wait");

    act(() => {
      vi.advanceTimersByTime(900);
    });

    expect(trigger).toHaveAttribute("data-phase", "model_wait");
  });

  it("shows each queued active Working phase for a visible interval", () => {
    vi.useFakeTimers();
    const items = [
      {
        kind: "thinking" as const,
        itemId: "thinking-1",
        title: "Thinking",
        content: "Planning",
      },
    ];
    const { rerender } = render(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "model_wait", message: "Analyzing..." }}
        itemsVersion={1}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Working/ });
    expect(trigger).toHaveAttribute("data-phase", "model_wait");

    rerender(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={2}
      />,
    );
    rerender(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "finalizing", message: "Finalizing..." }}
        itemsVersion={3}
      />,
    );

    expect(trigger).toHaveAttribute("data-phase", "model_wait");

    act(() => {
      vi.advanceTimersByTime(900);
    });

    expect(trigger).toHaveAttribute("data-phase", "tool_execution");

    act(() => {
      vi.advanceTimersByTime(899);
    });

    expect(trigger).toHaveAttribute("data-phase", "tool_execution");

    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(trigger).toHaveAttribute("data-phase", "finalizing");
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
    expect(trigger.querySelector('[data-component="text-shimmer"]')).toHaveAttribute("data-active", "true");
    expect(screen.queryByLabelText("running")).not.toBeInTheDocument();
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
    expect(trigger.querySelector('[data-component="text-shimmer"]')).toHaveAttribute("data-active", "true");
    expect(screen.queryByLabelText("running")).not.toBeInTheDocument();
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

  it("keeps Working details collapsed by default while a tool is running", () => {
    render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Run it",
            markdown: false,
          },
          {
            kind: "tool_group" as const,
            itemId: "tool-1",
            label: "shell",
            status: "running" as const,
            items: [
              {
                text: "ls -la",
                metadata: {
                  tool_name: "shell",
                  status: "running" as const,
                  command: "ls -la",
                },
              },
            ],
          },
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={1}
      />,
    );

    const workingButton = screen.getByRole("button", { name: /Working/ });
    expect(workingButton).toHaveAttribute("aria-expanded", "false");
    // The inner shell command text should not be in the DOM yet because the
    // collapsible defaults to closed for running tools.
    expect(screen.queryByText("ls -la")).not.toBeInTheDocument();
  });

  it("scrolls the timeline to the end of the expanded content when the user opens a running Working block", async () => {
    const items = [
      {
        kind: "message" as const,
        itemId: "user-1",
        role: "user" as const,
        content: "Run a long task",
        markdown: false,
      },
      {
        kind: "tool_group" as const,
        itemId: "tool-1",
        label: "shell",
        status: "running" as const,
        items: [
          {
            text: "tail -f /var/log/syslog\nstreaming line 1\nstreaming line 2",
            metadata: {
              tool_name: "shell",
              status: "running" as const,
              command: "tail -f /var/log/syslog",
            },
          },
        ],
      },
    ];

    const { container } = render(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running shell..." }}
        itemsVersion={1}
      />,
    );

    const scrollArea = container.querySelector<HTMLElement>(".session-scroll-area");
    expect(scrollArea).not.toBeNull();
    Object.defineProperties(scrollArea!, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 2000 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });

    const scrollSpy = vi.spyOn(scrollArea!, "scrollTo");

    const workingButton = screen.getByRole("button", { name: /Working/ });
    expect(workingButton).toHaveAttribute("aria-expanded", "false");

    await act(async () => {
      fireEvent.click(workingButton);
      // Flush the requestAnimationFrame inside the open handler.
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
    });

    expect(workingButton).toHaveAttribute("aria-expanded", "true");
    // The user-open handler must call scrollTo so the bottom of the
    // newly-expanded content is visible (i.e. the latest tool output).
    expect(scrollSpy).toHaveBeenCalled();
    const lastCall = scrollSpy.mock.calls.at(-1)?.[0] as ScrollToOptions;
    expect(lastCall.behavior).toBe("instant");
    // Either we landed on the very bottom of the timeline, or we advanced
    // toward it — never jumped above the prior position (which would have
    // been the "go to top" bug).
    expect((lastCall.top ?? 0)).toBeGreaterThanOrEqual(0);
  });

  it("does not jump the viewport when the user opens a completed historical Working block", async () => {
    const items = [
      {
        kind: "message" as const,
        itemId: "user-1",
        role: "user" as const,
        content: "Run a task",
        markdown: false,
      },
      {
        kind: "tool_group" as const,
        itemId: "tool-1",
        label: "shell",
        // No `status` field => completed historical tool group.
        items: [
          {
            text: "ls -la\nfile-a\nfile-b",
            metadata: {
              tool_name: "shell",
              command: "ls -la",
            },
          },
        ],
      },
      {
        kind: "message" as const,
        itemId: "assistant-1",
        role: "assistant" as const,
        content: "All done.",
        markdown: true,
      },
    ];

    const { container } = render(
      <SessionTimeline
        items={items}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        // Session is no longer active — the assistant final message has
        // arrived. The Working block is purely historical.
        processing={null}
        itemsVersion={1}
      />,
    );

    const scrollArea = container.querySelector<HTMLElement>(".session-scroll-area");
    expect(scrollArea).not.toBeNull();
    Object.defineProperties(scrollArea!, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 2000 },
      scrollTop: { configurable: true, writable: true, value: 600 },
    });

    const scrollSpy = vi.spyOn(scrollArea!, "scrollTo");
    // Drop any scrollTo calls triggered by the initial mount/new-item
    // effect — we only care about what happens when the user opens the
    // historical block.
    scrollSpy.mockClear();

    const workingButton = screen.getByRole("button", { name: /Working/ });
    // The closeSignal forces historical Working blocks closed once the
    // final assistant message arrives.
    expect(workingButton).toHaveAttribute("aria-expanded", "false");

    await act(async () => {
      fireEvent.click(workingButton);
      // Flush the requestAnimationFrame the user-open handler would have
      // scheduled if it were (incorrectly) wired for this WorkRun.
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
    });

    expect(workingButton).toHaveAttribute("aria-expanded", "true");
    // The historical block should expand silently — no programmatic scroll,
    // because that callback is reserved for the active running run.
    expect(scrollSpy).not.toHaveBeenCalled();
    // And the inner Collapsible content has actually mounted (i.e. the
    // expand worked even though we didn't run the user-open scroll path).
    expect(
      container.querySelector(".timeline-entry__work-run-body"),
    ).not.toBeNull();
  });

  it("keeps a completed apply_patch Working block collapsed unless the user opened it", () => {
    const userMessage = {
      kind: "message" as const,
      itemId: "user-1",
      role: "user" as const,
      content: "Apply the patch",
      markdown: false,
    };
    const applyPatchEntry = {
      text: "update_file TODO.md",
      classes: "tool-call-apply-patch",
      metadata: {
        tool_name: "apply_patch" as const,
        path: "TODO.md",
        operation: "update_file" as const,
        diff: "-[ ] Old\n+[X] New",
        call_id: "call_patch_running",
      },
    };
    const runningTool = {
      kind: "tool_group" as const,
      itemId: "tool-1",
      label: "apply_patch",
      status: "running" as const,
      items: [applyPatchEntry],
    };
    const runningItems = [userMessage, runningTool];

    const { rerender } = render(
      <SessionTimeline
        items={runningItems}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Applying..." }}
        itemsVersion={1}
      />,
    );

    // While running, the panel is collapsed.
    let workingButton = screen.getByRole("button", { name: /Working/ });
    expect(workingButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("TODO.md")).not.toBeInTheDocument();

    const completedItems = [
      userMessage,
      {
        ...runningTool,
        status: undefined,
        items: [
          {
            ...applyPatchEntry,
            metadata: {
              ...applyPatchEntry.metadata,
              success: true,
            },
          },
        ],
      },
    ];

    rerender(
      <SessionTimeline
        items={completedItems}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={null}
        itemsVersion={2}
      />,
    );

    // Once the run completes, the apply_patch diff stays collapsed until the
    // user opens this specific block.
    workingButton = screen.getByRole("button", { name: /Working/ });
    expect(workingButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("TODO.md")).not.toBeInTheDocument();

    workingButton = openWorking();

    expect(workingButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("TODO.md")[0]).toBeInTheDocument();
    expect(screen.getByText("Updated")).toBeInTheDocument();
  });

  it(
    "keeps the apply_patch Working block collapsed when tool completion and"
      + " the final assistant message arrive in the same update",
    async () => {
      const userMessage = {
        kind: "message" as const,
        itemId: "user-1",
        role: "user" as const,
        content: "Apply the patch",
        markdown: false,
      };
      const applyPatchEntry = {
        text: "update_file TODO.md",
        classes: "tool-call-apply-patch",
        metadata: {
          tool_name: "apply_patch" as const,
          path: "TODO.md",
          operation: "update_file" as const,
          diff: "-[ ] Old\n+[X] New",
          call_id: "call_patch_race",
        },
      };
      const runningTool = {
        kind: "tool_group" as const,
        itemId: "tool-1",
        label: "apply_patch",
        status: "running" as const,
        items: [applyPatchEntry],
      };

      const { rerender } = render(
        <SessionTimeline
          items={[userMessage, runningTool]}
          subAgents={{}}
          connection="connected"
          waitMessage={null}
          processing={{
            active: true,
            phase: "tool_execution",
            message: "Applying...",
          }}
          itemsVersion={1}
        />,
      );

      // While the tool is running the panel is collapsed.
      let workingButton = screen.getByRole("button", { name: /Working/ });
      expect(workingButton).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByText("TODO.md")).not.toBeInTheDocument();

      // Single render where the tool flips running -> completed AND the final
      // assistant response is appended. Completed apply_patch blocks must not
      // auto-open.
      const completedTool = {
        ...runningTool,
        status: undefined,
        items: [
          {
            ...applyPatchEntry,
            metadata: {
              ...applyPatchEntry.metadata,
              success: true,
            },
          },
        ],
      };
      rerender(
        <SessionTimeline
          items={[
            userMessage,
            completedTool,
            {
              kind: "message",
              itemId: "assistant-1",
              role: "assistant",
              content: "Done.",
              markdown: true,
            },
          ]}
          subAgents={{}}
          connection="connected"
          waitMessage={null}
          processing={null}
          itemsVersion={2}
        />,
      );

      await waitFor(() => {
        workingButton = screen.getByRole("button", { name: /Working/ });
        expect(workingButton).toHaveAttribute("aria-expanded", "false");
      });
      expect(screen.queryByText("TODO.md")).not.toBeInTheDocument();
    },
  );

  it("keeps the next Working block collapsed after an intermediate assistant message", () => {
    const firstTool = {
      kind: "tool_group" as const,
      itemId: "tool-1",
      label: "shell",
      status: undefined,
      items: [{ text: "first output" }],
    };
    const secondTool = {
      kind: "tool_group" as const,
      itemId: "tool-2",
      label: "apply_patch",
      status: "running" as const,
      items: [
        {
          text: "update_file NEXT.md",
          classes: "tool-call-apply-patch",
          metadata: {
            tool_name: "apply_patch" as const,
            path: "NEXT.md",
            operation: "update_file" as const,
            diff: "-[ ] Old\n+[X] New",
            call_id: "call_patch_next",
          },
        },
      ],
    };

    const { rerender } = render(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Do the work",
            markdown: false,
          },
          firstTool,
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running..." }}
        itemsVersion={1}
      />,
    );

    const firstWorkingButton = openWorking();
    expect(firstWorkingButton).toHaveAttribute("aria-expanded", "true");
expect(screen.getAllByText("first output")[0]).toBeInTheDocument();

    rerender(
      <SessionTimeline
        items={[
          {
            kind: "message",
            itemId: "user-1",
            role: "user",
            content: "Do the work",
            markdown: false,
          },
          firstTool,
          {
            kind: "message",
            itemId: "assistant-1",
            role: "assistant",
            content: "I found something; continuing.",
            markdown: true,
          },
          secondTool,
        ]}
        subAgents={{}}
        connection="connected"
        waitMessage={null}
        processing={{ active: true, phase: "tool_execution", message: "Running..." }}
        itemsVersion={2}
      />,
    );

    const workingButtons = screen.getAllByRole("button", { name: /Working/ });
    expect(workingButtons).toHaveLength(2);
    expect(workingButtons[0]).toHaveAttribute("aria-expanded", "true");
    expect(workingButtons[1]).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("NEXT.md")).not.toBeInTheDocument();
  });
});
