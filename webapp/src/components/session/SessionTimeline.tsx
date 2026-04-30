import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRightIcon } from "lucide-react";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import type {
  ProcessingPhase,
  ProcessingState,
  TimelineItem,
  TimelineMessageItem,
  TimelineThinkingItem,
  TimelineToolGroupItem,
} from "../../types";
import { Button } from "../ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { TimelineEntry } from "./TimelineEntry";
import { SessionWelcome } from "./SessionWelcome";
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
      // Keep running tools collapsed by default — opening them mid-stream
      // confuses the autoscroll. Completed apply_patch results stay open
      // so the diff is immediately visible.
      defaultOpen: !running && hasApplyPatch,
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

type WorkRunPhase = ProcessingPhase | "active";

function WorkRun({
  unit,
  subAgents,
  active,
  phase,
  closeSignal,
  onUserOpen,
}: {
  unit: Extract<RenderUnit, { kind: "work_run" }>;
  subAgents: Record<string, { title: string; status: string }>;
  active: boolean;
  phase: WorkRunPhase | null;
  closeSignal: string | null;
  onUserOpen?: (contentEl: HTMLElement | null) => void;
}) {
  const subAgent = unit.subAgentId ? subAgents[unit.subAgentId] : undefined;
  const hasItems = unit.items.length > 0;
  const lastItemId = hasItems ? unit.items[unit.items.length - 1].itemId : undefined;
  const [openState, setOpenState] = useState({
    open: unit.defaultOpen,
    closeSignal,
  });
  const open = openState.closeSignal === closeSignal ? openState.open : false;
  const contentRef = useRef<HTMLDivElement>(null);

  // When `unit.defaultOpen` flips from false -> true (e.g. an apply_patch
  // run finishes streaming and its diff should now be visible), reveal the
  // panel automatically. This restores the prior "diff is immediately
  // visible" behavior that was lost once running tools started rendering
  // collapsed: useState's initializer only runs once with the initial
  // (running) value, so a later defaultOpen flip would otherwise be a no-op.
  // We only force-open; we never force-close, so an explicit user toggle
  // continues to win on subsequent renders.
  //
  // Critical race: tool completion and the final assistant message can
  // arrive in the same render. In that case `closeSignal` also transitions
  // (null -> assistant itemId) and the close-signal logic intends to keep
  // the block collapsed. Skip the auto-open whenever `closeSignal` changed
  // in this same cycle so the final-answer close behavior wins.
  const previousDefaultOpenRef = useRef(unit.defaultOpen);
  const previousCloseSignalRef = useRef(closeSignal);
  useEffect(() => {
    const defaultOpenJustEnabled =
      !previousDefaultOpenRef.current && unit.defaultOpen;
    const closeSignalChanged = previousCloseSignalRef.current !== closeSignal;
    if (defaultOpenJustEnabled && !closeSignalChanged) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing with `unit.defaultOpen` derived from streaming tool status; we need to react to its transition false->true after the initial useState initializer captured the running (false) value.
      setOpenState((prev) =>
        prev.closeSignal === closeSignal && prev.open
          ? prev
          : { open: true, closeSignal },
      );
    }
    previousDefaultOpenRef.current = unit.defaultOpen;
    previousCloseSignalRef.current = closeSignal;
  }, [unit.defaultOpen, closeSignal]);

  return (
    <div
      className="timeline-entry timeline-entry--work-run"
      data-timeline-item-id={lastItemId}
    >
      <Collapsible
        open={open}
        onOpenChange={(nextOpen) => {
          setOpenState({ open: nextOpen, closeSignal });
          if (nextOpen) {
            onUserOpen?.(contentRef.current);
          }
        }}
      >
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="timeline-entry__header timeline-entry__header--work-run"
            data-phase={phase ?? undefined}
          >
            <ChevronRightIcon className="timeline-entry__chevron" />
            <span>Working</span>
            {active || unit.running ? (
              <span className="timeline-entry__running" aria-label="running" />
            ) : null}
          </Button>
        </CollapsibleTrigger>
        {hasItems ? (
          <CollapsibleContent>
            <div className="timeline-entry__work-run-body" ref={contentRef}>
              {unit.items.map((item) => (
                <TimelineEntry
                  key={item.itemId}
                  item={item}
                  subAgentTitle={subAgent?.title}
                  subAgentStatus={subAgent?.status}
                  closeSignal={closeSignal}
                  bare
                />
              ))}
            </div>
          </CollapsibleContent>
        ) : null}
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
  const baseRenderUnits = useMemo(() => buildRenderUnits(items), [items]);
  const sessionIsActive = Boolean(processing?.active || waitMessage);
  const activePhase: WorkRunPhase | null = sessionIsActive
    ? processing?.phase ?? "active"
    : null;
  const renderUnits = useMemo(() => {
    if (!sessionIsActive) return baseRenderUnits;
    const last = baseRenderUnits[baseRenderUnits.length - 1];
    if (last?.kind === "work_run") return baseRenderUnits;
    return [
      ...baseRenderUnits,
      {
        kind: "work_run" as const,
        key: "work-active-placeholder",
        items: [],
        subAgentId: undefined,
        running: true,
        defaultOpen: false,
      },
    ];
  }, [baseRenderUnits, sessionIsActive]);
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

  const closeCollapsiblesSignal =
    latestItem?.kind === "message" && latestItem.role === "assistant"
      ? latestItem.itemId
      : null;

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

  const handleUserOpenCollapsible = useCallback(
    (contentEl: HTMLElement | null) => {
      const container = containerRef.current;
      if (!container) return;
      // Treat a user-initiated open like fresh "follow the latest output"
      // intent: keep autoscroll glued to the bottom and dismiss any pending
      // "new messages" badge once we've scrolled.
      userScrolledRef.current = false;
      setShowNewMessages(false);
      const align = () => {
        if (!container.isConnected) return;
        markProgrammaticScroll();
        if (contentEl && contentEl.isConnected) {
          // Bring the bottom of the freshly expanded panel into view so the
          // latest tool output is visible without ever jumping the viewport
          // upward.
          const containerRect = container.getBoundingClientRect();
          const contentRect = contentEl.getBoundingClientRect();
          const delta = contentRect.bottom - containerRect.bottom;
          if (delta > 0) {
            const maxScrollTop = Math.max(
              0,
              container.scrollHeight - container.clientHeight,
            );
            container.scrollTo({
              top: Math.min(container.scrollTop + delta, maxScrollTop),
              behavior: "instant",
            });
            return;
          }
        }
        // Fallback: stick to the very bottom of the timeline.
        container.scrollTo({
          top: container.scrollHeight,
          behavior: "instant",
        });
      };
      // Wait one frame so the Collapsible has finished laying out its
      // content; otherwise the rect math runs against the pre-open layout.
      requestAnimationFrame(align);
    },
    [containerRef, markProgrammaticScroll, setShowNewMessages, userScrolledRef],
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
      // querySelectorAll + last picks the innermost match: when the new item
      // is rendered inside an expanded WorkRun the inner TimelineEntry shares
      // a data-timeline-item-id with the WorkRun wrapper, and a depth-first
      // querySelector would otherwise return the wrapper and scroll the user
      // away from the new content.
      const matches = container.querySelectorAll<HTMLElement>(
        `[data-timeline-item-id="${CSS.escape(latestItem.itemId)}"]`,
      );
      const target = matches.length > 0 ? matches.item(matches.length - 1) : null;

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
          <SessionWelcome />
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
                closeSignal={closeCollapsiblesSignal}
              />
            );
          }
          const isActiveUnit = unit.key === activeWorkRunKey;
          // Only the active/running WorkRun should treat user-opens as a
          // "follow the latest output" intent. Expanding a completed
          // historical block must not reset auto-follow or hide the
          // new-messages badge.
          const isActiveRunningUnit = isActiveUnit && unit.running;
          return (
            <WorkRun
              key={unit.key}
              unit={unit}
              subAgents={subAgents}
              active={isActiveUnit}
              phase={isActiveUnit ? activePhase : null}
              closeSignal={closeCollapsiblesSignal}
              onUserOpen={
                isActiveRunningUnit ? handleUserOpenCollapsible : undefined
              }
            />
          );
        })}
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
