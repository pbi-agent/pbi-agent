import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TimelineEntry } from "./TimelineEntry";
import { TooltipProvider } from "../ui/tooltip";
import type { TimelineItem } from "../../types";

function renderTimelineEntry(item: TimelineItem, props: Partial<Parameters<typeof TimelineEntry>[0]> = {}) {
  return render(<TimelineEntry item={item} {...props} />, {
    wrapper: TooltipProvider,
  });
}

function mockClipboardWrite(reject = false) {
  const writeText = reject
    ? vi.fn().mockRejectedValue(new Error("denied"))
    : vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  return writeText;
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: undefined,
  });
});

it("renders the compacted context marker with the opening separator only", () => {
  const item: TimelineItem = {
    kind: "message",
    itemId: "compact-system",
    role: "assistant",
    content: "[compacted context]",
    markdown: true,
  };

  const { container } = renderTimelineEntry(item);

  expect(screen.queryByText("[compacted context]")).not.toBeInTheDocument();
  expect(screen.getByText("compacted context")).toHaveClass(
    "timeline-entry__compaction-label",
  );
  expect(container.querySelector('[data-timeline-item-id="compact-system"]')).toHaveClass(
    "timeline-entry--compaction",
  );
  expect(container.querySelectorAll('[data-slot="separator"]')).toHaveLength(1);
  expect(container.querySelector(".timeline-entry__content")).not.toBeInTheDocument();
});

it("renders the closing separator after the compaction summary block", () => {
  const item: TimelineItem = {
    kind: "message",
    itemId: "compact-summary",
    role: "assistant",
    content: "[compacted context — reference only] summary\n\n## Details\nMore context.",
    markdown: true,
  };

  const { container } = renderTimelineEntry(item);

  expect(screen.getByText(/summary/)).toBeInTheDocument();
  expect(container.querySelector('[data-timeline-item-id="compact-summary"]')).toHaveClass(
    "timeline-entry--assistant",
  );
  expect(container.querySelector(".timeline-entry--compaction-summary-end")).toBeInTheDocument();
  expect(container.querySelectorAll('[data-slot="separator"]')).toHaveLength(1);
});

it("offers fork conversation for persisted assistant messages", async () => {
  const user = userEvent.setup();
  const onForkMessage = vi.fn();
  const item: TimelineItem = {
    kind: "message",
    itemId: "msg-2",
    messageId: "msg-2",
    role: "assistant",
    content: "answer",
    markdown: true,
  };

  renderTimelineEntry(item, { onForkMessage });

  await user.click(screen.getByRole("button", { name: "Fork conversation" }));

  expect(onForkMessage).toHaveBeenCalledWith("msg-2");
});

it("hides fork conversation for unpersisted messages", () => {
  const item: TimelineItem = {
    kind: "message",
    itemId: "message-1",
    role: "assistant",
    content: "live",
    markdown: true,
  };

  renderTimelineEntry(item, { onForkMessage: vi.fn() });

  expect(screen.queryByRole("button", { name: "Fork conversation" })).not.toBeInTheDocument();
});

it("hides fork conversation for user messages", () => {
  const item: TimelineItem = {
    kind: "message",
    itemId: "msg-3",
    messageId: "msg-3",
    role: "user",
    content: "hello",
    markdown: false,
  };

  renderTimelineEntry(item, { onForkMessage: vi.fn() });

  expect(screen.queryByRole("button", { name: "Fork conversation" })).not.toBeInTheDocument();
});

it("copies user turn content from the hover action row", async () => {
  const user = userEvent.setup();
  const writeText = mockClipboardWrite();
  const item: TimelineItem = {
    kind: "message",
    itemId: "msg-4",
    messageId: "msg-4",
    role: "user",
    content: "hello\nworld",
    markdown: false,
  };

  const { container } = renderTimelineEntry(item);

  expect(container.querySelector(".timeline-entry__actions")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Copy turn" }));

  expect(writeText).toHaveBeenCalledWith("hello\nworld");
  expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
});

it("shows a temporary check icon after copying a turn", async () => {
  const user = userEvent.setup();
  const setTimeoutSpy = vi.spyOn(window, "setTimeout");
  mockClipboardWrite();
  const item: TimelineItem = {
    kind: "message",
    itemId: "msg-copy-feedback",
    messageId: "msg-copy-feedback",
    role: "user",
    content: "copy me",
    markdown: false,
  };

  renderTimelineEntry(item);

  await user.click(screen.getByRole("button", { name: "Copy turn" }));

  const copiedButton = await screen.findByRole("button", { name: "Copied" });
  expect(copiedButton.querySelector(".lucide-check")).toBeInTheDocument();
  expect(setTimeoutSpy.mock.calls.some(([, delay]) => delay === 3000)).toBe(true);
});

it("copies assistant turn markdown source from the hover action row", async () => {
  const user = userEvent.setup();
  const writeText = mockClipboardWrite();
  const item: TimelineItem = {
    kind: "message",
    itemId: "msg-5",
    messageId: "msg-5",
    role: "assistant",
    content: "**Answer** with markdown",
    markdown: true,
  };

  renderTimelineEntry(item);

  await user.click(screen.getByRole("button", { name: "Copy turn" }));

  expect(writeText).toHaveBeenCalledWith("**Answer** with markdown");
  expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
});

it("copies code block snippets without copying the full turn", async () => {
  const user = userEvent.setup();
  const writeText = mockClipboardWrite();
  const item: TimelineItem = {
    kind: "message",
    itemId: "msg-6",
    messageId: "msg-6",
    role: "assistant",
    content: "Intro\n\n```ts\nconst value = 1;\n```\n\nOutro",
    markdown: true,
  };

  renderTimelineEntry(item);

  await user.click(screen.getByRole("button", { name: "Copy snippet" }));

  expect(writeText).toHaveBeenCalledWith("const value = 1;");
});

it("copies rendered markdown tables as readable tsv snippets", async () => {
  const user = userEvent.setup();
  const writeText = mockClipboardWrite();
  const item: TimelineItem = {
    kind: "message",
    itemId: "msg-7",
    messageId: "msg-7",
    role: "assistant",
    content: "| Name | Value |\n| --- | --- |\n| Alpha | 1 |\n| Beta | 2 |",
    markdown: true,
  };

  renderTimelineEntry(item);

  await user.click(screen.getByRole("button", { name: "Copy snippet" }));

  expect(writeText).toHaveBeenCalledWith("Name\tValue\nAlpha\t1\nBeta\t2");
});

it("copies rendered markdown block snippets only", async () => {
  const user = userEvent.setup();
  const writeText = mockClipboardWrite();
  const item: TimelineItem = {
    kind: "message",
    itemId: "msg-8",
    messageId: "msg-8",
    role: "assistant",
    content: "> quoted **note**",
    markdown: true,
  };

  renderTimelineEntry(item);

  await user.click(screen.getByRole("button", { name: "Copy snippet" }));

  expect(writeText).toHaveBeenCalledWith("quoted note");
});

it("shows a non-blocking copy failure state", async () => {
  const user = userEvent.setup();
  const writeText = mockClipboardWrite(true);
  const item: TimelineItem = {
    kind: "message",
    itemId: "msg-9",
    messageId: "msg-9",
    role: "user",
    content: "cannot copy",
    markdown: false,
  };

  renderTimelineEntry(item);

  await user.click(screen.getByRole("button", { name: "Copy turn" }));

  expect(writeText).toHaveBeenCalledWith("cannot copy");
  expect(await screen.findByRole("button", { name: "Copy failed" })).toBeInTheDocument();
});
