import { describe, expect, it } from "vitest";
import {
  projectMainTimelineItems,
  projectSubAgentTimelineItems,
  projectionSignature,
  timelineItemSubAgentId,
} from "./sessionTimelineProjection";
import type { TimelineItem, TimelineMessageItem } from "./types";

function message(itemId: string, content: string): TimelineMessageItem {
  return {
    kind: "message",
    itemId,
    role: "assistant",
    content,
    markdown: true,
  };
}

describe("session timeline projection", () => {
  it("collapses sub-agent transcript churn into stable main-session cards", () => {
    const baseItems: TimelineItem[] = [
      message("parent-user", "Research this"),
      {
        kind: "thinking",
        itemId: "sub-think-1",
        title: "Thinking",
        content: "Initial child plan",
        subAgentId: "sub-1",
      },
    ];
    const updatedItems: TimelineItem[] = [
      message("parent-user", "Research this"),
      {
        kind: "thinking",
        itemId: "sub-think-1",
        title: "Thinking",
        content: "Updated child plan",
        subAgentId: "sub-1",
      },
      {
        kind: "tool_group",
        itemId: "sub-tool-1",
        label: "read_file",
        status: "running",
        items: [{ text: "reading" }],
        subAgentId: "sub-1",
      },
    ];

    const baseProjection = projectMainTimelineItems(baseItems);
    const updatedProjection = projectMainTimelineItems(updatedItems);

    expect(baseProjection.signature).toBe(updatedProjection.signature);
    expect(updatedProjection.items).toEqual([
      message("parent-user", "Research this"),
      expect.objectContaining({
        kind: "thinking",
        itemId: "sub-agent-card:sub-1:sub-think-1",
        content: "",
        subAgentId: "sub-1",
      }),
    ]);
  });

  it("keeps distinct sub-agent cards and top-level updates visible in the main projection", () => {
    const projection = projectMainTimelineItems([
      message("parent-user", "Research this"),
      {
        kind: "thinking",
        itemId: "sub-a-think",
        title: "Thinking",
        content: "A",
        subAgentId: "sub-a",
      },
      {
        kind: "thinking",
        itemId: "sub-b-think",
        title: "Thinking",
        content: "B",
        subAgentId: "sub-b",
      },
      message("parent-assistant", "Done"),
    ]);

    expect(projection.items.map((item) => item.itemId)).toEqual([
      "parent-user",
      "sub-agent-card:sub-a:sub-a-think",
      "sub-agent-card:sub-b:sub-b-think",
      "parent-assistant",
    ]);
  });

  it("keeps full transcript items for a selected sub-agent route", () => {
    const projection = projectSubAgentTimelineItems([
      message("parent", "Parent"),
      {
        kind: "message",
        itemId: "sub-user",
        role: "user",
        content: "Child task",
        markdown: false,
        subAgentId: "sub-1",
      },
      {
        kind: "message",
        itemId: "sub-answer",
        role: "assistant",
        content: "Child answer",
        markdown: true,
        subAgentId: "sub-1",
      },
    ], "sub-1");

    expect(projection.items.map((item) => item.itemId)).toEqual([
      "sub-user",
      "sub-answer",
    ]);
    expect(projection.signature).toContain("Child answer");
  });

  it("recovers sub-agent ownership from persisted item ids when old messages lack sub-agent fields", () => {
    const projection = projectSubAgentTimelineItems([
      message("run-1:parent-message", "Parent"),
      {
        kind: "message",
        itemId: "run-1:subagent-25-message-1",
        role: "user",
        content: "Delegated task",
        markdown: false,
      },
      {
        kind: "tool_group",
        itemId: "run-1:subagent-25-tool-group-2",
        label: "read_file",
        status: "completed",
        items: [{ text: "read_file" }],
        subAgentId: "run-1:subagent-25",
      },
      {
        kind: "message",
        itemId: "run-1:subagent-25-message-3",
        role: "assistant",
        content: "Delegated answer",
        markdown: true,
      },
    ], "run-1:subagent-25");

    expect(projection.items.map((item) => item.itemId)).toEqual([
      "run-1:subagent-25-message-1",
      "run-1:subagent-25-tool-group-2",
      "run-1:subagent-25-message-3",
    ]);
    expect(projection.signature).toContain("Delegated answer");
  });

  it("uses inferred sub-agent ownership when collapsing old child items in the main timeline", () => {
    const projection = projectMainTimelineItems([
      message("parent-message", "Parent"),
      {
        kind: "message",
        itemId: "run-1:subagent-25-message-1",
        role: "assistant",
        content: "Old child message without subAgentId",
        markdown: true,
      },
      {
        kind: "tool_group",
        itemId: "run-1:subagent-25-tool-group-2",
        label: "read_file",
        items: [{ text: "read_file" }],
        subAgentId: "run-1:subagent-25",
      },
    ]);

    expect(timelineItemSubAgentId(projection.items[1])).toBe("run-1:subagent-25");
    expect(projection.items.map((item) => item.itemId)).toEqual([
      "parent-message",
      "sub-agent-card:run-1:subagent-25:run-1:subagent-25-message-1",
    ]);
  });

  it("serializes timeline signatures without delimiter collisions", () => {
    const first = projectionSignature([
      message("message\0child", "same content"),
    ]);
    const second = projectionSignature([
      {
        ...message("message", "same content"),
        messageId: "child\0",
      },
    ]);

    expect(first).not.toBe(second);
  });
});
