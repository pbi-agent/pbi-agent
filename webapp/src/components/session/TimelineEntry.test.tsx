import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TimelineEntry } from "./TimelineEntry";
import { TooltipProvider } from "../ui/tooltip";
import type { TimelineItem } from "../../types";

it("renders the compacted context marker with the opening separator only", () => {
  const item: TimelineItem = {
    kind: "message",
    itemId: "compact-system",
    role: "assistant",
    content: "[compacted context]",
    markdown: true,
  };

  const { container } = render(<TimelineEntry item={item} />);

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

  const { container } = render(<TimelineEntry item={item} />);

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

  render(<TimelineEntry item={item} onForkMessage={onForkMessage} />, {
    wrapper: TooltipProvider,
  });

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

  render(<TimelineEntry item={item} onForkMessage={vi.fn()} />);

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

  render(<TimelineEntry item={item} onForkMessage={vi.fn()} />);

  expect(screen.queryByRole("button", { name: "Fork conversation" })).not.toBeInTheDocument();
});
