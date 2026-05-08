import { render, screen } from "@testing-library/react";
import { TimelineEntry } from "./TimelineEntry";
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
