import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BotIcon, ChevronRightIcon } from "lucide-react";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import type { ConnectionState } from "../../store";
import type {
  ProcessingPhase,
  ProcessingState,
  TimelineItem,
  TimelineMessageItem,
  TimelineThinkingItem,
  TimelineToolGroupItem,
  TimelineToolGroupEntry,
  ToolCallMetadata,
} from "../../types";
import { Button } from "../ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { Badge } from "../ui/badge";
import { MarkdownContent } from "../shared/MarkdownContent";
import { ToolResult } from "./ToolResult";
import { TimelineEntry } from "./TimelineEntry";
import { SessionWelcome } from "./SessionWelcome";

const USER_MESSAGE_TOP_OFFSET = 8;
const ASSISTANT_MESSAGE_TOP_OFFSET = 8;
const WORK_RUN_PHASE_MIN_VISIBLE_MS = 600;
const WORK_RUN_PHASE_TRANSITION_MS = 300;
const WORK_RUN_PHASE_HOLD_MS =
  WORK_RUN_PHASE_MIN_VISIBLE_MS + WORK_RUN_PHASE_TRANSITION_MS;

type WorkItem = TimelineMessageItem | TimelineThinkingItem | TimelineToolGroupItem;

type RenderUnit =
  | { kind: "message"; item: TimelineMessageItem }
  | {
      kind: "work_run";
      key: string;
      items: WorkItem[];
      running: boolean;
    };

function shouldCoalesceInWorkRun(
  item: TimelineItem,
  options: { showSubAgentCards: boolean },
): boolean {
  const { showSubAgentCards } = options;
  return item.kind === "thinking"
    || item.kind === "tool_group"
    || (showSubAgentCards && Boolean(item.subAgentId));
}

function buildRenderUnits(
  items: TimelineItem[],
  options: { showSubAgentCards: boolean },
): RenderUnit[] {
  const { showSubAgentCards } = options;
  const units: RenderUnit[] = [];
  let buffer: WorkItem[] = [];
  let previousMessageItemId: string | undefined;
  let workRunSinceMessage = false;

  const flush = () => {
    if (buffer.length === 0) return;
    const running = buffer.some((it) =>
      it.kind === "tool_group" && it.status === "running",
    );
    units.push({
      kind: "work_run",
      key:
        previousMessageItemId && !workRunSinceMessage
          ? `work-after-${previousMessageItemId}`
          : `work-${buffer[0].itemId}`,
      items: buffer,
      running,
    });
    buffer = [];
    workRunSinceMessage = true;
  };

  for (const item of items) {
    if (!shouldCoalesceInWorkRun(item, { showSubAgentCards })) {
      flush();
      if (item.kind === "message") {
        units.push({ kind: "message", item });
        previousMessageItemId = item.itemId;
        workRunSinceMessage = false;
      }
      continue;
    }
    buffer.push(item);
  }
  flush();
  return units;
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function toolNameFor(metadata: ToolCallMetadata | undefined, fallback: string) {
  return stringValue(metadata?.tool_name) ?? fallback;
}

function toolItemStatus(toolItem: TimelineToolGroupEntry): string | null {
  if (toolItem.metadata?.status) return toolItem.metadata.status;
  if (toolItem.metadata?.success === true) return "completed";
  if (toolItem.metadata?.success === false) return "failed";
  return null;
}

type ToolCategory = "read" | "search" | "list" | "shell" | "edit" | "sub-agent" | "other";

function categorizeTool(toolName: string): ToolCategory {
  if (["read_file", "read_image", "read_web_url"].includes(toolName)) return "read";
  if (["web_search", "grep", "glob", "search"].includes(toolName)) return "search";
  if (["list", "ls"].includes(toolName)) return "list";
  if (toolName === "shell") return "shell";
  if (["apply_patch", "write_file", "replace_in_file"].includes(toolName)) return "edit";
  if (toolName === "sub_agent") return "sub-agent";
  return "other";
}

function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function summarizeCounts(entries: ToolListEntry[]) {
  const labels: Record<ToolCategory, string> = {
    read: "read",
    search: "search",
    list: "list",
    shell: "shell",
    edit: "edit",
    "sub-agent": "sub-agent",
    other: "other",
  };
  const counts = new Map<ToolCategory, number>();
  for (const entry of entries) {
    counts.set(entry.category, (counts.get(entry.category) ?? 0) + 1);
  }
  return (["read", "search", "list", "shell", "edit", "sub-agent", "other"] as ToolCategory[])
    .map((category) => {
      const count = counts.get(category) ?? 0;
      return count > 0 ? pluralize(count, labels[category]) : null;
    })
    .filter((label): label is string => Boolean(label))
    .join(", ");
}

type ToolListEntry = {
  key: string;
  itemId: string;
  label: string;
  entry: TimelineToolGroupEntry;
  category: ToolCategory;
  status: string | null;
};

type WorkingGroup =
  | { kind: "thinking"; key: string; items: TimelineThinkingItem[] }
  | { kind: "tools"; key: string; entries: ToolListEntry[]; running: boolean }
  | { kind: "sub_agent"; key: string; subAgentId: string; items: WorkItem[]; running: boolean };

function buildWorkingGroups(items: WorkItem[], showSubAgentCards: boolean): WorkingGroup[] {
  const groups: WorkingGroup[] = [];
  let thinkingBuffer: TimelineThinkingItem[] = [];
  let toolBuffer: ToolListEntry[] = [];
  let subAgentBufferId: string | null = null;
  let subAgentBufferItems: WorkItem[] = [];
  let subAgentBufferRunning = false;
  const subAgentGroups = new Map<
    string,
    Extract<WorkingGroup, { kind: "sub_agent" }>
  >();

  const flushThinking = () => {
    if (thinkingBuffer.length === 0) return;
    groups.push({ kind: "thinking", key: `thinking-${thinkingBuffer[0].itemId}`, items: thinkingBuffer });
    thinkingBuffer = [];
  };
  const flushTools = () => {
    if (toolBuffer.length === 0) return;
    groups.push({
      kind: "tools",
      key: `tools-${toolBuffer[0].key}`,
      entries: toolBuffer,
      running: toolBuffer.some((entry) => entry.status === "running"),
    });
    toolBuffer = [];
  };
  const flushSubAgent = () => {
    if (!subAgentBufferId || subAgentBufferItems.length === 0) return;
    const group: Extract<WorkingGroup, { kind: "sub_agent" }> = {
      kind: "sub_agent",
      key: `sub-agent-${subAgentBufferId}-${subAgentBufferItems[0].itemId}`,
      subAgentId: subAgentBufferId,
      items: subAgentBufferItems,
      running: subAgentBufferRunning,
    };
    groups.push(group);
    subAgentGroups.set(subAgentBufferId, group);
    subAgentBufferId = null;
    subAgentBufferItems = [];
    subAgentBufferRunning = false;
  };

  for (const item of items) {
    if (showSubAgentCards && item.subAgentId) {
      flushThinking();
      flushTools();
      const running = item.kind === "tool_group" && item.status === "running";
      const existingGroup = subAgentGroups.get(item.subAgentId);
      if (existingGroup) {
        existingGroup.items = [...existingGroup.items, item];
        existingGroup.running = existingGroup.running || running;
        continue;
      }
      if (subAgentBufferId === item.subAgentId) {
        subAgentBufferItems = [...subAgentBufferItems, item];
        subAgentBufferRunning = subAgentBufferRunning || running;
      } else {
        flushSubAgent();
        subAgentBufferId = item.subAgentId;
        subAgentBufferItems = [item];
        subAgentBufferRunning = running;
      }
      continue;
    }
    flushSubAgent();
    if (item.kind === "thinking") {
      flushTools();
      thinkingBuffer.push(item);
      continue;
    }
    if (item.kind === "message") {
      continue;
    }
    flushThinking();
    item.items.forEach((entry, index) => {
      const label = toolNameFor(entry.metadata, item.label);
      const status = toolItemStatus(entry) ?? item.status ?? null;
      const category = categorizeTool(label);
      toolBuffer.push({
        key: `${item.itemId}-${index}`,
        itemId: item.itemId,
        label,
        entry,
        category,
        status,
      });
    });
  }
  flushSubAgent();
  flushThinking();
  flushTools();
  return groups;
}

function toolSubtitle(entry: ToolListEntry) {
  const args = objectValue(entry.entry.metadata?.arguments);
  const result = objectValue(entry.entry.metadata?.result);
  return (
    stringValue(entry.entry.metadata?.path)
    ?? stringValue(result?.path)
    ?? stringValue(args?.path)
    ?? stringValue(entry.entry.metadata?.command)
    ?? stringValue(args?.command)
    ?? stringValue(result?.url)
    ?? stringValue(args?.url)
    ?? entry.entry.text.split("\n")[0]
  );
}

function subAgentDisplayName(title: string | undefined, fallback: string): string {
  return title?.split("·", 1)[0]?.trim() || title || fallback;
}

function subAgentStatusModifier(status: string): "completed" | "failed" | "idle" | "running" {
  if (status === "running" || status === "starting") return "running";
  if (status === "failed" || status === "error") return "failed";
  if (status === "completed") return "completed";
  return "idle";
}

function SubAgentCard({
  group,
  subAgents,
  parentSessionId,
}: {
  group: Extract<WorkingGroup, { kind: "sub_agent" }>;
  subAgents: Record<string, { title: string; status: string }>;
  parentSessionId?: string;
}) {
  const navigate = useNavigate();
  const agent = subAgents[group.subAgentId];
  const status = agent?.status ?? (group.running ? "running" : "completed");
  const name = subAgentDisplayName(agent?.title, group.subAgentId);
  const statusModifier = subAgentStatusModifier(status);
  return (
    <button
      type="button"
      className="working-items__sub-agent-card"
      aria-label={`Open ${name} agent session`}
      onClick={() => {
        if (parentSessionId) {
          void navigate(`/sessions/${encodeURIComponent(parentSessionId)}/sub-agents/${encodeURIComponent(group.subAgentId)}`);
        }
      }}
      disabled={!parentSessionId}
    >
      <BotIcon />
      <span className="working-items__sub-agent-main">{name}</span>
      <Badge variant="secondary" className={`working-items__sub-agent-status status-pill status-pill--${statusModifier}`}>
        {status}
      </Badge>
    </button>
  );
}

function WorkingItemsPanel({
  items,
  subAgents,
  closeSignal,
  parentSessionId,
  showSubAgentCards = true,
}: {
  items: WorkItem[];
  subAgents: Record<string, { title: string; status: string }>;
  closeSignal: string | null;
  parentSessionId?: string;
  showSubAgentCards?: boolean;
}) {
  const groups = useMemo(() => buildWorkingGroups(items, showSubAgentCards), [items, showSubAgentCards]);
  const [openGroupsState, setOpenGroupsState] = useState<{
    closeSignal: string | null;
    groups: Record<string, boolean>;
  }>({ closeSignal, groups: {} });
  const [openToolsState, setOpenToolsState] = useState<{
    closeSignal: string | null;
    tools: Record<string, boolean>;
  }>({ closeSignal, tools: {} });
  const openGroups = openGroupsState.closeSignal === closeSignal
    ? openGroupsState.groups
    : {};
  const openTools = openToolsState.closeSignal === closeSignal
    ? openToolsState.tools
    : {};

  return (
    <div className="working-items">
      {groups.map((group) => {
        if (group.kind === "sub_agent") {
          return <SubAgentCard key={group.key} group={group} subAgents={subAgents} parentSessionId={parentSessionId} />;
        }
        const open = Boolean(openGroups[group.key]);
        const isThinking = group.kind === "thinking";
        const summary = isThinking
          ? pluralize(group.items.length, "thinking block")
          : summarizeCounts(group.entries);
        return (
          <Collapsible
            key={group.key}
            open={open}
            onOpenChange={(nextOpen) => setOpenGroupsState((prev) => ({
              closeSignal,
              groups: {
                ...(prev.closeSignal === closeSignal ? prev.groups : {}),
                [group.key]: nextOpen,
              },
            }))}
          >
            <CollapsibleTrigger asChild>
              <Button type="button" variant="ghost" size="sm" className="working-items__group-trigger">
                <ChevronRightIcon className="timeline-entry__chevron" />
                <span>{isThinking ? "Thinking" : group.running ? "Using tools" : "Used tools"}</span>
                <span className="working-items__summary">{summary}</span>
                {group.kind === "tools" && group.running ? <span className="timeline-entry__running" aria-label="running" /> : null}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="working-items__level-2">
                {isThinking
                  ? group.items.map((item) => (
                    <div key={item.itemId} className="working-items__thinking-detail" data-timeline-item-id={item.itemId}>
                      <MarkdownContent content={item.content} />
                    </div>
                  ))
                  : group.entries.map((entry) => {
                    const toolOpen = Boolean(openTools[entry.key]);
                    return (
                      <Collapsible
                        key={entry.key}
                        open={toolOpen}
                        onOpenChange={(nextOpen) => setOpenToolsState((prev) => ({
                          closeSignal,
                          tools: {
                            ...(prev.closeSignal === closeSignal ? prev.tools : {}),
                            [entry.key]: nextOpen,
                          },
                        }))}
                      >
                        <CollapsibleTrigger asChild>
                          <Button type="button" variant="ghost" size="sm" className="working-items__tool-trigger" data-timeline-item-id={entry.itemId}>
                            <ChevronRightIcon className="timeline-entry__chevron" />
                            <span className="working-items__tool-title">{entry.label}</span>
                            <span className="working-items__tool-subtitle">{toolSubtitle(entry)}</span>
                            {entry.status === "running" ? <span className="timeline-entry__running" aria-label="running" /> : null}
                          </Button>
                        </CollapsibleTrigger>
                        <CollapsibleContent>
                          <div className="working-items__tool-detail">
                            <ToolResult
                              metadata={entry.entry.metadata}
                              text={entry.entry.text}
                              running={entry.status === "running"}
                            />
                          </div>
                        </CollapsibleContent>
                      </Collapsible>
                    );
                  })}
              </div>
            </CollapsibleContent>
          </Collapsible>
        );
      })}
    </div>
  );
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

function useVisibleWorkRunPhase(phase: WorkRunPhase | null) {
  const [visiblePhase, setVisiblePhase] = useState(phase);
  const visiblePhaseRef = useRef(phase);
  const visibleSinceRef = useRef(0);
  const queuedPhasesRef = useRef<WorkRunPhase[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current === null) return;
    clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  const markVisiblePhase = useCallback((nextPhase: WorkRunPhase | null) => {
    visiblePhaseRef.current = nextPhase;
    visibleSinceRef.current = Date.now();
  }, []);

  const setVisiblePhaseNow = useCallback(
    (nextPhase: WorkRunPhase | null) => {
      markVisiblePhase(nextPhase);
      setVisiblePhase(nextPhase);
    },
    [markVisiblePhase],
  );

  const scheduleNextPhase = useCallback(
    function scheduleQueuedPhase() {
      if (timerRef.current !== null || queuedPhasesRef.current.length === 0) {
        return;
      }

      const elapsed = Date.now() - visibleSinceRef.current;
      const delay = Math.max(WORK_RUN_PHASE_HOLD_MS - elapsed, 0);
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        const nextPhase = queuedPhasesRef.current.shift();
        if (!nextPhase) return;
        setVisiblePhaseNow(nextPhase);
        scheduleQueuedPhase();
      }, delay);
    },
    [setVisiblePhaseNow],
  );

  useEffect(() => {
    if (visiblePhaseRef.current !== null && visibleSinceRef.current === 0) {
      visibleSinceRef.current = Date.now();
    }
  }, []);

  useEffect(() => {
    if (phase === null) {
      queuedPhasesRef.current = [];
      clearTimer();
      if (visiblePhaseRef.current !== null) {
        markVisiblePhase(null);
        setTimeout(() => {
          setVisiblePhase(null);
        }, 0);
      }
      return;
    }

    if (visiblePhaseRef.current === null) {
      markVisiblePhase(phase);
      setTimeout(() => {
        setVisiblePhase(phase);
      }, 0);
      return;
    }

    if (phase === visiblePhaseRef.current) {
      queuedPhasesRef.current = [];
      clearTimer();
      return;
    }

    const queuedPhaseIndex = queuedPhasesRef.current.indexOf(phase);
    if (queuedPhaseIndex !== -1) {
      queuedPhasesRef.current = queuedPhasesRef.current.slice(
        0,
        queuedPhaseIndex + 1,
      );
      scheduleNextPhase();
      return;
    }

    queuedPhasesRef.current.push(phase);
    scheduleNextPhase();
  }, [clearTimer, markVisiblePhase, phase, scheduleNextPhase]);

  useEffect(
    () => () => {
      clearTimer();
    },
    [clearTimer],
  );

  return visiblePhase;
}

function WorkRun({
  unit,
  subAgents,
  active,
  phase,
  closeSignal,
  onUserOpen,
  parentSessionId,
  showSubAgentCards,
}: {
  unit: Extract<RenderUnit, { kind: "work_run" }>;
  subAgents: Record<string, { title: string; status: string }>;
  active: boolean;
  phase: WorkRunPhase | null;
  closeSignal: string | null;
  onUserOpen?: (contentEl: HTMLElement | null) => void;
  parentSessionId?: string;
  showSubAgentCards?: boolean;
}) {
  const hasItems = unit.items.length > 0;
  const lastItemId = hasItems ? unit.items[unit.items.length - 1].itemId : undefined;
  const [openState, setOpenState] = useState({
    open: false,
    closeSignal,
  });
  const open = openState.closeSignal === closeSignal ? openState.open : false;
  const contentRef = useRef<HTMLDivElement>(null);

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
            aria-label="Working"
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
              <WorkingItemsPanel
                items={unit.items}
                subAgents={subAgents}
                closeSignal={closeSignal}
                parentSessionId={parentSessionId}
                showSubAgentCards={showSubAgentCards}
              />
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
  parentSessionId,
  showSubAgentCards = true,
}: {
  items: TimelineItem[];
  subAgents: Record<string, { title: string; status: string }>;
  connection: ConnectionState;
  waitMessage: string | null;
  processing: ProcessingState | null;
  itemsVersion: number;
  parentSessionId?: string;
  showSubAgentCards?: boolean;
}) {
  const previousLengthRef = useRef<number | undefined>(undefined);
  const latestItem = items.at(-1);
  const latestItemIsUserMessage =
    latestItem?.kind === "message" && latestItem.role === "user";
  const baseRenderUnits = useMemo(
    () => buildRenderUnits(items, { showSubAgentCards }),
    [items, showSubAgentCards],
  );
  const sessionIsActive = Boolean(processing?.active || waitMessage);
  const activePhase: WorkRunPhase | null = sessionIsActive
    ? processing?.phase ?? "active"
    : null;
  const visibleActivePhase = useVisibleWorkRunPhase(activePhase);
  const renderUnits = useMemo(() => {
    if (!sessionIsActive) return baseRenderUnits;
    const last = baseRenderUnits[baseRenderUnits.length - 1];
    if (last?.kind === "work_run") return baseRenderUnits;
    return [
      ...baseRenderUnits,
      {
        kind: "work_run" as const,
        key: latestItem?.kind === "message"
          ? `work-after-${latestItem.itemId}`
          : "work-active-placeholder",
        items: [],
        running: true,
      },
    ];
  }, [baseRenderUnits, latestItem, sessionIsActive]);
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
              phase={isActiveUnit ? visibleActivePhase : null}
              closeSignal={closeCollapsiblesSignal}
              onUserOpen={
                isActiveRunningUnit ? handleUserOpenCollapsible : undefined
              }
              parentSessionId={parentSessionId}
              showSubAgentCards={showSubAgentCards}
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
