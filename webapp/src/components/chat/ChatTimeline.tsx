import { useCallback, useEffect, useRef } from "react";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import type { TimelineItem } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { TimelineEntry } from "./TimelineEntry";

const USER_MESSAGE_TOP_OFFSET = 8;
const ASSISTANT_MESSAGE_TOP_OFFSET = 8;

/**
 * Wait for all images inside `container` to finish loading so that
 * offsetTop calculations account for the final layout.  Resolves
 * immediately when there are no pending images.
 */
function waitForImages(container: HTMLElement): Promise<void> {
  const imgs = container.querySelectorAll<HTMLImageElement>("img");
  const pending = Array.from(imgs).filter((img) => !img.complete);
  if (pending.length === 0) return Promise.resolve();
  return Promise.all(
    pending.map(
      (img) =>
        new Promise<void>((resolve) => {
          img.addEventListener("load", () => resolve(), { once: true });
          img.addEventListener("error", () => resolve(), { once: true });
        }),
    ),
  ).then(() => {});
}

export function ChatTimeline({
  items,
  subAgents,
  connection,
}: {
  items: TimelineItem[];
  subAgents: Record<string, { title: string; status: string }>;
  connection: "disconnected" | "connecting" | "connected";
}) {
  const previousLengthRef = useRef<number>();
  const latestItem = items.at(-1);
  const latestItemIsUserMessage =
    latestItem?.kind === "message" && latestItem.role === "user";
  const { containerRef, showNewMessages, setShowNewMessages, scrollToBottom, userScrolledRef } =
    useAutoScroll([items.length], { followOnChange: false });

  const scrollToTarget = useCallback(
    (container: HTMLElement, target: HTMLElement, offset: number) => {
      container.scrollTo({
        top: Math.max(target.offsetTop - offset, 0),
        behavior: "smooth",
      });
    },
    [],
  );

  useEffect(() => {
    const previousLength = previousLengthRef.current;
    previousLengthRef.current = items.length;
    if (previousLength === undefined || items.length <= previousLength) {
      return;
    }

    const container = containerRef.current;
    if (!container || !latestItem) {
      return;
    }

    const target = container.querySelector<HTMLElement>(
      `[data-timeline-item-id="${CSS.escape(latestItem.itemId)}"]`,
    );
    if (!target) {
      return;
    }

    if (latestItemIsUserMessage) {
      waitForImages(container).then(() => {
        scrollToTarget(container, target, USER_MESSAGE_TOP_OFFSET);
      });
      userScrolledRef.current = false;
    } else if (!userScrolledRef.current) {
      waitForImages(container).then(() => {
        scrollToTarget(container, target, ASSISTANT_MESSAGE_TOP_OFFSET);
      });
      userScrolledRef.current = true;
    } else {
      setShowNewMessages(true);
    }
  }, [containerRef, items.length, latestItem, latestItemIsUserMessage, userScrolledRef, setShowNewMessages, scrollToTarget]);

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
