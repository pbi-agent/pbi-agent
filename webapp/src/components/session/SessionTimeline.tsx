import { useCallback, useEffect, useMemo, useRef } from "react";
import { ChevronRightIcon } from "lucide-react";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import type {
  ProcessingState,
  TimelineItem,
  TimelineMessageItem,
  TimelineThinkingItem,
  TimelineToolGroupItem,
} from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { Button } from "../ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { TimelineEntry } from "./TimelineEntry";
import { isApplyPatchToolMetadata } from "./GitDiffResult";

const USER_MESSAGE_TOP_OFFSET = 8;
const ASSISTANT_MESSAGE_TOP_OFFSET = 8;

type WorkItem = TimelineThinkingItem | TimelineToolGroupItem;

type RenderUnit =
  | { kind: "message"; item: TimelineMessageItem }
  | {
      kind: "work_run";
      key: string;
      items: WorkItem[];
      subAgentId: string | undefined;
      running: boolean;
      defaultOpen: boolean;
    };

function isWorkItem(item: TimelineItem): item is WorkItem {
  return item.kind === "thinking" || item.kind === "tool_group";
}

function buildRenderUnits(items: TimelineItem[]): RenderUnit[] {
  const units: RenderUnit[] = [];
  let buffer: WorkItem[] = [];
  let bufferSubAgent: string | undefined;

  const flush = () => {
    if (buffer.length === 0) return;
    const running = buffer.some(
      (it) => it.kind === "tool_group" && it.status === "running",
    );
    const hasApplyPatch = buffer.some(
      (it) =>
        it.kind === "tool_group"
        && it.items.some(
          (entry) =>
            isApplyPatchToolMetadata(entry.metadata)
            && Boolean(entry.metadata.diff),
        ),
    );
    units.push({
      kind: "work_run",
      key: `work-${buffer[0].itemId}`,
      items: buffer,
      subAgentId: bufferSubAgent,
      running,
      defaultOpen: running || hasApplyPatch,
    });
    buffer = [];
    bufferSubAgent = undefined;
  };

  for (const item of items) {
    if (!isWorkItem(item)) {
      flush();
      units.push({ kind: "message", item });
      continue;
    }
    if (buffer.length > 0 && bufferSubAgent !== item.subAgentId) {
      flush();
    }
    if (buffer.length === 0) {
      bufferSubAgent = item.subAgentId;
    }
    buffer.push(item);
  }
  flush();
  return units;
}

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

function WorkRun({
  unit,
  subAgents,
  active,
}: {
  unit: Extract<RenderUnit, { kind: "work_run" }>;
  subAgents: Record<string, { title: string; status: string }>;
  active: boolean;
}) {
  const subAgent = unit.subAgentId ? subAgents[unit.subAgentId] : undefined;
  const lastItemId = unit.items[unit.items.length - 1].itemId;

  return (
    <div
      className="timeline-entry timeline-entry--work-run"
      data-timeline-item-id={lastItemId}
    >
      <Collapsible defaultOpen={unit.defaultOpen}>
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="timeline-entry__header timeline-entry__header--work-run"
          >
            <ChevronRightIcon className="timeline-entry__chevron" />
            <span>Working</span>
            {active || unit.running ? (
              <span className="timeline-entry__running" aria-label="running" />
            ) : null}
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="timeline-entry__work-run-body">
            {unit.items.map((item) => (
              <TimelineEntry
                key={item.itemId}
                item={item}
                subAgentTitle={subAgent?.title}
                subAgentStatus={subAgent?.status}
                bare
              />
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

export function SessionTimeline({
  items,
  subAgents,
  connection,
  waitMessage,
  processing,
  itemsVersion,
}: {
  items: TimelineItem[];
  subAgents: Record<string, { title: string; status: string }>;
  connection: "disconnected" | "connecting" | "connected";
  waitMessage: string | null;
  processing: ProcessingState | null;
  itemsVersion: number;
}) {
  const previousLengthRef = useRef<number | undefined>(undefined);
  const latestItem = items.at(-1);
  const latestItemIsUserMessage =
    latestItem?.kind === "message" && latestItem.role === "user";
  const renderUnits = useMemo(() => buildRenderUnits(items), [items]);
  const sessionIsActive = Boolean(processing?.active || waitMessage);
  const latestRenderUnit = renderUnits[renderUnits.length - 1];
  const activeWorkRunKey =
    sessionIsActive && latestRenderUnit?.kind === "work_run"
      ? latestRenderUnit.key
      : null;
  const {
    containerRef,
    showNewMessages,
    setShowNewMessages,
    scrollToBottom,
    userScrolledRef,
    markProgrammaticScroll,
  } =
    useAutoScroll(itemsVersion, { followOnChange: false });

  const scrollToTarget = useCallback(
    (container: HTMLElement, target: HTMLElement, offset: number) => {
      markProgrammaticScroll();
      container.scrollTo({
        top: Math.max(target.offsetTop - offset, 0),
        behavior: "instant",
      });
    },
    [markProgrammaticScroll],
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
        markProgrammaticScroll();
        container.scrollTo({ top: container.scrollHeight, behavior: "instant" });
      } else {
        setShowNewMessages(true);
      }
    }
  }, [containerRef, itemsVersion, items.length, latestItem, latestItemIsUserMessage, userScrolledRef, setShowNewMessages, scrollToTarget, markProgrammaticScroll]);

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
        {renderUnits.map((unit) => {
          if (unit.kind === "message") {
            return (
              <TimelineEntry
                key={unit.item.itemId}
                item={unit.item}
                subAgentTitle={
                  unit.item.subAgentId
                    ? subAgents[unit.item.subAgentId]?.title
                    : undefined
                }
                subAgentStatus={
                  unit.item.subAgentId
                    ? subAgents[unit.item.subAgentId]?.status
                    : undefined
                }
              />
            );
          }
          return (
            <WorkRun
              key={unit.key}
              unit={unit}
              subAgents={subAgents}
              active={unit.key === activeWorkRunKey}
            />
          );
        })}
        {processing?.active ? (
          <div className={`processing-indicator processing-indicator--${processing.phase ?? "active"}`}>
            <div className="spinner spinner--sm" />
            <span>{processing.message ?? "Working..."}</span>
          </div>
        ) : waitMessage ? (
          <div className="processing-indicator">
            <div className="spinner spinner--sm" />
            <span>{waitMessage}</span>
          </div>
        ) : null}
        {showNewMessages ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="timeline__new-messages"
            onClick={scrollToBottom}
          >
            New messages below
          </Button>
        ) : null}
      </div>
    </div>
  );
}
