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

export function SessionTimeline({
  items,
  subAgents,
  connection,
  waitMessage,
  itemsVersion,
}: {
  items: TimelineItem[];
  subAgents: Record<string, { title: string; status: string }>;
  connection: "disconnected" | "connecting" | "connected";
  waitMessage: string | null;
  itemsVersion: number;
}) {
  const previousLengthRef = useRef<number | undefined>(undefined);
  const latestItem = items.at(-1);
  const latestItemIsUserMessage =
    latestItem?.kind === "message" && latestItem.role === "user";
  const { containerRef, showNewMessages, setShowNewMessages, scrollToBottom, userScrolledRef } =
    useAutoScroll(itemsVersion, { followOnChange: false });

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

    const container = containerRef.current;
    if (!container) return;

    const isNewItem =
      previousLength !== undefined && items.length > previousLength;

    if (isNewItem && latestItem) {
      // New item added — scroll to the top of that item
      const target = container.querySelector<HTMLElement>(
        `[data-timeline-item-id="${CSS.escape(latestItem.itemId)}"]`,
      );

      if (latestItemIsUserMessage) {
        // Always scroll to user messages
        if (target) {
          void waitForImages(container).then(() => {
            scrollToTarget(container, target, USER_MESSAGE_TOP_OFFSET);
          });
        }
        userScrolledRef.current = false;
      } else if (!userScrolledRef.current) {
        // Scroll to top of new assistant/tool/thinking item
        if (target) {
          void waitForImages(container).then(() => {
            scrollToTarget(container, target, ASSISTANT_MESSAGE_TOP_OFFSET);
          });
        }
      } else {
        setShowNewMessages(true);
      }
    } else if (!isNewItem) {
      // Existing item content updated — stick to bottom
      if (!userScrolledRef.current) {
        container.scrollTo({ top: container.scrollHeight, behavior: "instant" });
      } else {
        setShowNewMessages(true);
      }
    }
  }, [containerRef, itemsVersion, items.length, latestItem, latestItemIsUserMessage, userScrolledRef, setShowNewMessages, scrollToTarget]);

  if (items.length === 0 && connection === "connected") {
    return (
      <div className="session-scroll-area" ref={containerRef}>
        <div className="timeline">
          <EmptyState
            title="Session started. Waiting for updates…"
            description="Live events will appear here as soon as the session produces output."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="session-scroll-area" ref={containerRef}>
      <div className="timeline">
        {items.map((item) => (
          <TimelineEntry
            key={item.itemId}
            item={item}
            subAgentTitle={item.subAgentId ? subAgents[item.subAgentId]?.title : undefined}
            subAgentStatus={item.subAgentId ? subAgents[item.subAgentId]?.status : undefined}
          />
        ))}
        {waitMessage ? (
          <div className="processing-indicator">
            <div className="spinner spinner--sm" />
            <span>{waitMessage}</span>
          </div>
        ) : null}
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
    </div>
  );
}
