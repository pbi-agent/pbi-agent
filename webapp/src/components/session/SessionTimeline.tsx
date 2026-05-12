import { memo, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
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
const WORKING_ITEMS_MAX_VISIBLE = 5;
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

const GENERIC_RETRY_MESSAGE_PATTERN = /^Retrying\.\.\. \(\d+\/\d+\)$/;

function isGenericRetryMessageItem(item: TimelineItem): boolean {
  return item.kind === "message"
    && (item.role === "notice" || item.role === "error")
    && GENERIC_RETRY_MESSAGE_PATTERN.test(item.content.trim());
}

function timelineItemChangeKey(item: TimelineItem): string {
  if (item.kind === "message") {
    return [
      item.kind,
      item.itemId,
      item.role,
      item.content,
      item.filePaths?.join("\0") ?? "",
      item.imageAttachments?.map((attachment) => attachment.upload_id).join("\0") ?? "",
    ].join("\0");
  }
  if (item.kind === "thinking") {
    return [item.kind, item.itemId, item.title, item.content].join("\0");
  }
  return [
    item.kind,
    item.itemId,
    item.label,
    item.status ?? "",
    ...item.items.map((entry) => [
      entry.text,
      entry.classes ?? "",
      JSON.stringify(entry.metadata ?? null),
    ].join("\0")),
  ].join("\0");
}

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

const KNOWN_TOOL_NAMES = new Set([
  "apply_patch",
  "ask_user",
  "read_file",
  "read_image",
  "read_web_url",
  "replace_in_file",
  "shell",
  "sub_agent",
  "web_search",
  "write_file",
]);

function normalizeToolNameCandidate(value: string | undefined): string | undefined {
  if (!value) return undefined;
  return value.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function toolNameFromClasses(classes: string | undefined): string | undefined {
  if (!classes) return undefined;
  for (const className of classes.split(/\s+/)) {
    if (!className.startsWith("tool-call-")) continue;
    const toolName = normalizeToolNameCandidate(className.slice("tool-call-".length));
    if (toolName) return toolName;
  }
  return undefined;
}

function toolNameFromText(text: string): string | undefined {
  return normalizeToolNameCandidate(text.match(/[A-Za-z][\w-]*/)?.[0]);
}

function knownToolName(value: string | undefined): string | undefined {
  return value && KNOWN_TOOL_NAMES.has(value) ? value : undefined;
}

function toolNameFor(entry: TimelineToolGroupEntry, groupLabel: string) {
  const metadataToolName = stringValue(entry.metadata?.tool_name);
  if (metadataToolName) return normalizeToolNameCandidate(metadataToolName) ?? metadataToolName;
  return (
    knownToolName(toolNameFromClasses(entry.classes))
    ?? knownToolName(normalizeToolNameCandidate(groupLabel))
    ?? knownToolName(toolNameFromText(entry.text))
    ?? groupLabel
  );
}

function friendlyToolName(toolName: string) {
  const labels: Record<string, string> = {
    apply_patch: "Edit",
    ask_user: "Ask user",
    read_file: "Read",
    read_image: "Inspect image",
    read_web_url: "Read webpage",
    replace_in_file: "Update",
    shell: "Command",
    sub_agent: "Ask agent",
    web_search: "Search web",
    write_file: "Write",
  };
  return labels[toolName] ?? (
    toolName
      .split("_")
      .filter(Boolean)
      .map((part) => part[0]?.toUpperCase() + part.slice(1))
      .join(" ")
  );
}

function toolItemStatus(toolItem: TimelineToolGroupEntry): string | null {
  if (toolItem.metadata?.status) return toolItem.metadata.status;
  if (toolItem.metadata?.success === true) return "completed";
  if (toolItem.metadata?.success === false) return "failed";
  return null;
}

type ToolCategory = "read" | "search" | "list" | "shell" | "edit" | "sub-agent" | "question" | "other";

function categorizeTool(toolName: string): ToolCategory {
  if (["read_file", "read_image", "read_web_url"].includes(toolName)) return "read";
  if (["web_search", "grep", "glob", "search"].includes(toolName)) return "search";
  if (["list", "ls"].includes(toolName)) return "list";
  if (toolName === "shell") return "shell";
  if (["apply_patch", "write_file", "replace_in_file"].includes(toolName)) return "edit";
  if (toolName === "sub_agent") return "sub-agent";
  if (toolName === "ask_user") return "question";
  return "other";
}

function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

type CountSummaryItem = {
  key: string;
  count: number;
  singular: string;
  plural: string;
};

function summaryItemLabel(item: CountSummaryItem) {
  return pluralize(item.count, item.singular, item.plural);
}

function summarizeCountItems(items: CountSummaryItem[]) {
  return items
    .filter((item) => item.count > 0)
    .map(summaryItemLabel)
    .join(", ");
}

function categoryCountItems(counts: Map<ToolCategory, number>): CountSummaryItem[] {
  const labels: Record<ToolCategory, { singular: string; plural: string }> = {
    read: { singular: "read", plural: "reads" },
    search: { singular: "search", plural: "searches" },
    list: { singular: "list", plural: "lists" },
    shell: { singular: "shell", plural: "shells" },
    edit: { singular: "edit", plural: "edits" },
    "sub-agent": { singular: "agent", plural: "agents" },
    question: { singular: "question", plural: "questions" },
    other: { singular: "other", plural: "others" },
  };
  return (["read", "search", "list", "shell", "edit", "sub-agent", "question", "other"] as ToolCategory[]).map((category) => ({
    key: category,
    count: counts.get(category) ?? 0,
    singular: labels[category].singular,
    plural: labels[category].plural,
  }));
}

function toolEntriesForGroup(item: TimelineToolGroupItem): ToolListEntry[] {
  return item.items.map((entry, index) => {
    const label = toolNameFor(entry, item.label);
    const status = toolItemStatus(entry) ?? item.status ?? null;
    const category = categorizeTool(label);
    return {
      key: `${item.itemId}-${index}`,
      itemId: item.itemId,
      label,
      displayLabel: friendlyToolName(label),
      entry,
      category,
      status,
    };
  });
}

function summarizeWorkRun(items: WorkItem[], showSubAgentCards: boolean) {
  return summarizeCountItems(workRunCountItems(items, showSubAgentCards));
}

function workRunCountItems(items: WorkItem[], showSubAgentCards: boolean): CountSummaryItem[] {
  let thinkingCount = 0;
  const categoryCounts = new Map<ToolCategory, number>();
  const subAgentIds = new Set<string>();

  for (const item of items) {
    if (showSubAgentCards && item.subAgentId) {
      subAgentIds.add(item.subAgentId);
      continue;
    }
    if (item.kind === "thinking") {
      thinkingCount += 1;
      continue;
    }
    if (item.kind !== "tool_group") continue;
    for (const entry of toolEntriesForGroup(item)) {
      categoryCounts.set(entry.category, (categoryCounts.get(entry.category) ?? 0) + 1);
    }
  }

  if (showSubAgentCards) {
    categoryCounts.set("sub-agent", (categoryCounts.get("sub-agent") ?? 0) + subAgentIds.size);
  }

  return [
    { key: "thought", count: thinkingCount, singular: "thought", plural: "thoughts" },
    ...categoryCountItems(categoryCounts),
  ];
}

type ToolListEntry = {
  key: string;
  itemId: string;
  label: string;
  displayLabel: string;
  entry: TimelineToolGroupEntry;
  category: ToolCategory;
  status: string | null;
};

type WorkingGroup =
  | { kind: "thinking"; key: string; items: TimelineThinkingItem[] }
  | { kind: "tool"; key: string; entry: ToolListEntry }
  | { kind: "sub_agent"; key: string; subAgentId: string; items: WorkItem[]; running: boolean };

function buildWorkingGroups(items: WorkItem[], showSubAgentCards: boolean): WorkingGroup[] {
  const groups: WorkingGroup[] = [];
  let thinkingBuffer: TimelineThinkingItem[] = [];
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
      thinkingBuffer.push(item);
      continue;
    }
    if (item.kind === "message") {
      continue;
    }
    flushThinking();
    groups.push(...toolEntriesForGroup(item).map((entry) => ({
      kind: "tool" as const,
      key: `tool-${entry.key}`,
      entry,
    })));
  }
  flushSubAgent();
  flushThinking();
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

const ANIMATED_NUMBER_TRACK = Array.from({ length: 30 }, (_, index) => index % 10);

function normalizeDigit(value: number) {
  return ((value % 10) + 10) % 10;
}

function digitSpin(from: number, to: number, direction: 1 | -1) {
  if (from === to) return 0;
  if (direction > 0) return (to - from + 10) % 10;
  return -((from - to + 10) % 10);
}

function AnimatedNumberDigit({ value, direction }: { value: number; direction: 1 | -1 }) {
  const [state, setState] = useState({
    step: value + 10,
    animating: false,
    lastValue: value,
    direction,
  });

  if (state.lastValue !== value || state.direction !== direction) {
    const delta = digitSpin(state.lastValue, value, direction);
    if (delta === 0) {
      setState({ step: value + 10, animating: false, lastValue: value, direction });
    } else {
      setState({
        step: state.step + delta,
        animating: true,
        lastValue: value,
        direction,
      });
    }
  }

  return (
    <span data-slot="animated-number-digit">
      <span
        data-slot="animated-number-strip"
        data-animating={state.animating ? "true" : "false"}
        onTransitionEnd={() => {
          setState((current) => ({
            ...current,
            animating: false,
            step: normalizeDigit(current.step) + 10,
          }));
        }}
        style={{
          "--animated-number-offset": state.step,
        } as CSSProperties}
      >
        {ANIMATED_NUMBER_TRACK.map((digit, index) => (
          <span key={`${digit}-${index}`} data-slot="animated-number-cell" data-digit={digit} />
        ))}
      </span>
    </span>
  );
}

function AnimatedNumber({ value }: { value: number }) {
  const target = Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0;
  const [state, setState] = useState({ displayValue: target, direction: 1 as 1 | -1 });

  if (state.displayValue !== target) {
    setState({
      displayValue: target,
      direction: target > state.displayValue ? 1 : -1,
    });
  }

  const label = state.displayValue.toString();
  const digits = Array.from(label, (char) => {
    const digit = Number.parseInt(char, 10);
    return Number.isNaN(digit) ? 0 : digit;
  }).reverse();

  return (
    <span data-component="animated-number" className="animated-count-number">
      <span className="animated-count-number__text">{label}</span>
      <span
        data-slot="animated-number-value"
        aria-hidden="true"
        style={{
          "--animated-number-width": `${digits.length}ch`,
        } as CSSProperties}
      >
        {digits.map((digit, index) => (
          <AnimatedNumberDigit key={index} value={digit} direction={state.direction} />
        ))}
      </span>
    </span>
  );
}

function AnimatedCountSummary({
  items,
  className,
}: {
  items: CountSummaryItem[];
  className?: string;
}) {
  const visible = items.filter((item) => item.count > 0);
  if (visible.length === 0) return null;

  return (
    <span data-component="tool-count-summary" className={className}>
      {visible.map((item, index) => (
        <span key={item.key} data-slot="tool-count-summary-item">
          {index > 0 ? <span data-slot="tool-count-summary-prefix">, </span> : null}
          <span data-component="tool-count-label">
            <AnimatedNumber value={item.count} />
            <span data-slot="tool-count-label-space"> </span>
            <span data-slot="tool-count-label-word">
              {item.count === 1 ? item.singular : item.plural}
            </span>
          </span>
        </span>
      ))}
    </span>
  );
}

function TextShimmer({
  text,
  active = true,
  className,
}: {
  text: string;
  active?: boolean;
  className?: string;
}) {
  return (
    <span
      data-component="text-shimmer"
      data-active={active ? "true" : "false"}
      className={className}
      aria-label={text}
    >
      <span data-slot="text-shimmer-char">
        <span data-slot="text-shimmer-char-base" aria-hidden="true">
          {text}
        </span>
        <span
          data-slot="text-shimmer-char-shimmer"
          data-run={active ? "true" : "false"}
          data-text={text}
          aria-hidden="true"
        />
      </span>
    </span>
  );
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
      <Badge
        variant={statusModifier === "idle" ? "secondary" : statusModifier}
        size="meta"
        className="working-items__sub-agent-status"
      >
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const groupRefs = useRef(new Map<string, HTMLDivElement>());
  const needsScroll = groups.length > WORKING_ITEMS_MAX_VISIBLE;
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

  const lastGroupKey = groups.at(-1)?.key ?? null;

  useEffect(() => {
    if (!needsScroll) return;
    const scrollEl = scrollRef.current;
    if (!scrollEl) return;
    scrollEl.scrollTop = scrollEl.scrollHeight;
  }, [lastGroupKey, needsScroll]);

  const setGroupRef = useCallback((key: string) => (node: HTMLDivElement | null) => {
    if (node) {
      groupRefs.current.set(key, node);
      return;
    }
    groupRefs.current.delete(key);
  }, []);

  const scrollGroupToCenter = useCallback((key: string) => {
    if (!needsScroll) return;
    const scrollEl = scrollRef.current;
    const groupEl = groupRefs.current.get(key);
    if (!scrollEl || !groupEl) return;
    const scrollRect = scrollEl.getBoundingClientRect();
    const groupRect = groupEl.getBoundingClientRect();
    const centeredOffset = (scrollEl.clientHeight - Math.min(groupRect.height, scrollEl.clientHeight)) / 2;
    const targetTop = scrollEl.scrollTop + groupRect.top - scrollRect.top - centeredOffset;
    const maxTop = Math.max(0, scrollEl.scrollHeight - scrollEl.clientHeight);
    scrollEl.scrollTo({
      top: Math.min(Math.max(0, targetTop), maxTop),
      behavior: "smooth",
    });
  }, [needsScroll]);

  const scheduleScrollGroupToCenter = useCallback((key: string) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => scrollGroupToCenter(key));
    });
  }, [scrollGroupToCenter]);

  return (
    <div
      className={`working-items${needsScroll ? " working-items--scrollable" : ""}`}
      ref={scrollRef}
    >
      {groups.map((group) => {
        if (group.kind === "sub_agent") {
          return (
            <div key={group.key} ref={setGroupRef(group.key)} className="working-items__item">
              <SubAgentCard group={group} subAgents={subAgents} parentSessionId={parentSessionId} />
            </div>
          );
        }
        if (group.kind === "tool") {
          const entry = group.entry;
          const toolOpen = Boolean(openTools[entry.key]);
          return (
            <Collapsible
              key={group.key}
              open={toolOpen}
              onOpenChange={(nextOpen) => {
                setOpenToolsState((prev) => ({
                  closeSignal,
                  tools: {
                    ...(prev.closeSignal === closeSignal ? prev.tools : {}),
                    [entry.key]: nextOpen,
                  },
                }));
                if (nextOpen) scheduleScrollGroupToCenter(group.key);
              }}
            >
              <div ref={setGroupRef(group.key)} className="working-items__item">
                <CollapsibleTrigger asChild>
                  <Button type="button" variant="ghost" size="sm" className="working-items__tool-trigger" data-timeline-item-id={entry.itemId}>
                    <ChevronRightIcon className="timeline-entry__chevron" />
                    <span className="working-items__tool-title">{entry.displayLabel}</span>
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
              </div>
            </Collapsible>
          );
        }
        const open = Boolean(openGroups[group.key]);
        const groupLabel = "Thinking";
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
            <div ref={setGroupRef(group.key)} className="working-items__item">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="working-items__group-trigger"
                  aria-label={groupLabel}
                >
                  <ChevronRightIcon className="timeline-entry__chevron" />
                  <span>{groupLabel}</span>
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent>
                {group.items.map((item) => (
                  <div key={item.itemId} className="working-items__thinking-detail" data-timeline-item-id={item.itemId}>
                    <MarkdownContent content={item.content} />
                  </div>
                ))}
              </CollapsibleContent>
            </div>
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

const ACTIVE_WORK_RUN_PLACEHOLDER_KEY = "work-active-placeholder";

function shouldUseActivePlaceholderKey(unit: Extract<RenderUnit, { kind: "work_run" }>) {
  return !unit.key.startsWith("work-after-");
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
  const workRunSummary = useMemo(
    () => summarizeWorkRun(unit.items, showSubAgentCards ?? true),
    [showSubAgentCards, unit.items],
  );
  const workRunSummaryItems = useMemo(
    () => workRunCountItems(unit.items, showSubAgentCards ?? true),
    [showSubAgentCards, unit.items],
  );
  const hasRunningSubAgent = useMemo(
    () => unit.items.some((item) => {
      if (!item.subAgentId) return false;
      const status = subAgents[item.subAgentId]?.status;
      return status === "running" || status === "starting";
    }),
    [subAgents, unit.items],
  );
  const hasVisibleSummary = workRunSummaryItems.some((item) => item.count > 0);
  const isVisiblyActive = active || unit.running || hasRunningSubAgent;
  const showPlaceholderSummary = active && !hasVisibleSummary;

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
            aria-label={workRunSummary ? `Working ${workRunSummary}` : "Working"}
          >
            <ChevronRightIcon className="timeline-entry__chevron" />
            <TextShimmer text="Working" active={isVisiblyActive} className="timeline-entry__working-label" />
            {showPlaceholderSummary ? (
              <span className="working-items__summary working-items__summary--placeholder" aria-hidden="true">
                Preparing…
              </span>
            ) : (
              <AnimatedCountSummary items={workRunSummaryItems} className="working-items__summary" />
            )}
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

type SessionTimelineProps = {
  items: TimelineItem[];
  subAgents: Record<string, { title: string; status: string }>;
  connection: ConnectionState;
  waitMessage: string | null;
  processing: ProcessingState | null;
  itemsVersion: number | string;
  parentSessionId?: string;
  showSubAgentCards?: boolean;
  onForkMessage?: (messageId: string) => void;
};

function processingStatesEqual(
  left: ProcessingState | null,
  right: ProcessingState | null,
): boolean {
  if (left === right) return true;
  if (!left || !right) return false;
  return left.active === right.active
    && left.phase === right.phase
    && left.message === right.message
    && left.active_tool_count === right.active_tool_count;
}

function subAgentSummariesEqual(
  left: Record<string, { title: string; status: string }>,
  right: Record<string, { title: string; status: string }>,
): boolean {
  const leftEntries = Object.entries(left);
  const rightEntries = Object.entries(right);
  if (leftEntries.length !== rightEntries.length) return false;
  return leftEntries.every(([subAgentId, leftSubAgent]) => {
    const rightSubAgent = right[subAgentId];
    return rightSubAgent !== undefined
      && leftSubAgent.title === rightSubAgent.title
      && leftSubAgent.status === rightSubAgent.status;
  });
}

function areSessionTimelinePropsEqual(
  previous: SessionTimelineProps,
  next: SessionTimelineProps,
): boolean {
  return previous.itemsVersion === next.itemsVersion
    && previous.connection === next.connection
    && previous.waitMessage === next.waitMessage
    && processingStatesEqual(previous.processing, next.processing)
    && previous.parentSessionId === next.parentSessionId
    && previous.showSubAgentCards === next.showSubAgentCards
    && previous.onForkMessage === next.onForkMessage
    && subAgentSummariesEqual(previous.subAgents, next.subAgents);
}

export const SessionTimeline = memo(function SessionTimeline({
  items,
  subAgents,
  connection,
  waitMessage,
  processing,
  itemsVersion,
  parentSessionId,
  showSubAgentCards = true,
  onForkMessage,
}: SessionTimelineProps) {
  const previousLengthRef = useRef<number | undefined>(undefined);
  const previousItemsVersionRef = useRef<number | string | undefined>(undefined);
  const previousVisibleItemsChangeKeyRef = useRef<string | undefined>(undefined);
  const latestRawItem = items.at(-1);
  const visibleItems = useMemo(
    () => items.filter((item) => !isGenericRetryMessageItem(item)),
    [items],
  );
  const visibleItemsChangeKey = useMemo(
    () => visibleItems.map(timelineItemChangeKey).join("\n"),
    [visibleItems],
  );
  const latestItem = visibleItems.at(-1);
  const latestItemIsUserMessage =
    latestItem?.kind === "message" && latestItem.role === "user";
  const latestUserMessageHasImages =
    latestItemIsUserMessage && Boolean(latestItem.imageAttachments?.length);
  const baseRenderUnits = useMemo(
    () => buildRenderUnits(visibleItems, { showSubAgentCards }),
    [visibleItems, showSubAgentCards],
  );
  const sessionIsActive = Boolean(processing?.active || waitMessage);
  const activePhase: WorkRunPhase | null = sessionIsActive
    ? processing?.phase ?? "active"
    : null;
  const visibleActivePhase = useVisibleWorkRunPhase(activePhase);
  const renderUnits = useMemo(() => {
    if (!sessionIsActive) return baseRenderUnits;
    const last = baseRenderUnits[baseRenderUnits.length - 1];
    if (last?.kind === "work_run") {
      if (!shouldUseActivePlaceholderKey(last)) return baseRenderUnits;
      return [
        ...baseRenderUnits.slice(0, -1),
        {
          ...last,
          key: ACTIVE_WORK_RUN_PLACEHOLDER_KEY,
        },
      ];
    }
    return [
      ...baseRenderUnits,
      {
        kind: "work_run" as const,
        key: latestItem?.kind === "message"
          ? `work-after-${latestItem.itemId}`
          : ACTIVE_WORK_RUN_PLACEHOLDER_KEY,
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
    useAutoScroll(visibleItemsChangeKey, { followOnChange: false });

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

  const scrollToTargetBottomIfNeeded = useCallback(
    (container: HTMLElement, target: HTMLElement) => {
      if (!container.isConnected || !target.isConnected) return;
      const containerRect = container.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const delta = targetRect.bottom - containerRect.bottom;
      if (delta <= 0) return;
      const maxScrollTop = Math.max(0, container.scrollHeight - container.clientHeight);
      markProgrammaticScroll();
      container.scrollTo({
        top: Math.min(container.scrollTop + delta, maxScrollTop),
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
    const previousItemsVersion = previousItemsVersionRef.current;
    const previousVisibleItemsChangeKey = previousVisibleItemsChangeKeyRef.current;
    previousLengthRef.current = visibleItems.length;
    previousItemsVersionRef.current = itemsVersion;
    previousVisibleItemsChangeKeyRef.current = visibleItemsChangeKey;

    if (
      previousVisibleItemsChangeKey !== undefined
      && previousVisibleItemsChangeKey === visibleItemsChangeKey
      && previousItemsVersion === itemsVersion
    ) {
      return;
    }

    if (
      previousVisibleItemsChangeKey !== undefined
      && previousVisibleItemsChangeKey === visibleItemsChangeKey
      && latestRawItem
      && isGenericRetryMessageItem(latestRawItem)
    ) {
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    const isNewItem =
      previousLength !== undefined && visibleItems.length > previousLength;

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
            if (latestUserMessageHasImages) {
              scrollToTargetBottomIfNeeded(container, target);
            } else {
              scrollToTarget(container, target, USER_MESSAGE_TOP_OFFSET);
            }
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
  }, [containerRef, itemsVersion, latestRawItem, visibleItemsChangeKey, visibleItems.length, latestItem, latestItemIsUserMessage, latestUserMessageHasImages, userScrolledRef, setShowNewMessages, scrollToTarget, scrollToTargetBottomIfNeeded, markProgrammaticScroll]);

  if (visibleItems.length === 0 && connection === "connected" && !sessionIsActive) {
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
                onForkMessage={onForkMessage}
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
}, areSessionTimelinePropsEqual);
