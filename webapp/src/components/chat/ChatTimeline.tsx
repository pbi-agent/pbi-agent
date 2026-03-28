import { useAutoScroll } from "../../hooks/useAutoScroll";
import type { TimelineItem } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { TimelineEntry } from "./TimelineEntry";

export function ChatTimeline({
  items,
  subAgents,
  connection,
}: {
  items: TimelineItem[];
  subAgents: Record<string, { title: string; status: string }>;
  connection: "disconnected" | "connecting" | "connected";
}) {
  const { containerRef, showNewMessages, scrollToBottom } = useAutoScroll([items.length]);

  if (items.length === 0 && connection === "connected") {
    return (
      <div className="timeline" ref={containerRef}>
        <EmptyState
          title="No messages yet"
          description="Send a message to start the conversation"
        />
      </div>
    );
  }

  return (
    <div className="timeline" ref={containerRef}>
      {items.map((item) => (
        <TimelineEntry
          key={item.itemId}
          item={item}
          subAgentTitle={item.subAgentId ? subAgents[item.subAgentId]?.title : undefined}
          subAgentStatus={item.subAgentId ? subAgents[item.subAgentId]?.status : undefined}
        />
      ))}
      {showNewMessages ? (
        <button
          type="button"
          className="timeline__new-messages"
          onClick={scrollToBottom}
        >
          New messages below
        </button>
      ) : null}
    </div>
  );
}
