import { Fragment, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import { BotIcon, CheckIcon, ChevronDownIcon, ChevronRightIcon, ChevronUpIcon } from "lucide-react";
import { Accordion as AccordionPrimitive } from "radix-ui";
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
import {
  Accordion,
  AccordionItem,
} from "../ui/accordion";
import { Badge } from "../ui/badge";
import { MarkdownContent } from "../shared/MarkdownContent";
import { ToolResult } from "./ToolResult";
import { TimelineEntry } from "./TimelineEntry";
import { SessionWelcome } from "./SessionWelcome";
import {
  WorkingSummary,
  workingSummaryText,
  type CountSummaryItem,
} from "./WorkingSummary";

const USER_MESSAGE_TOP_OFFSET = 8;
const ASSISTANT_MESSAGE_TOP_OFFSET = 8;
const WORKING_ITEMS_MAX_VISIBLE = 5;
const WORKING_ITEMS_OPEN_GUTTER_PX = 16;
const WORKING_ITEMS_OPEN_MAX_VH = 0.7;
const WORK_RUN_OPEN_BOTTOM_GUTTER_PX = 16;
const WORK_RUN_OPEN_LAYOUT_SETTLE_MS = 260;
const WORK_RUN_PHASE_MIN_VISIBLE_MS = 600;
const WORK_RUN_PHASE_TRANSITION_MS = 300;
const WORK_RUN_PHASE_HOLD_MS =
  WORK_RUN_PHASE_MIN_VISIBLE_MS + WORK_RUN_PHASE_TRANSITION_MS;

type WorkItem = TimelineMessageItem | TimelineThinkingItem | TimelineToolGroupItem;
type SubAgentSummary = {
  title: string;
  status: string;
  turnElapsedSeconds?: number | null;
  turnCostUsd?: number | null;
};

type RenderUnit =
  | { kind: "message"; item: TimelineMessageItem }
  | {
      kind: "work_run";
      key: string;
      items: WorkItem[];
      running: boolean;
    };

type TurnSummary = {
  key: string;
  items: CountSummaryItem[];
  durationSeconds: number | null;
  costUsd: number | null;
};

const liveTickListeners = new Set<() => void>();
let liveTickInterval: ReturnType<typeof setInterval> | null = null;
let liveTickNowMs = Date.now();

function ensureLiveTickInterval() {
  if (liveTickInterval !== null) return;
  liveTickNowMs = Date.now();
  liveTickInterval = setInterval(() => {
    liveTickNowMs = Date.now();
    for (const listener of liveTickListeners) listener();
  }, 1000);
}

function subscribeLiveTick(listener: () => void) {
  liveTickListeners.add(listener);
  ensureLiveTickInterval();
  liveTickNowMs = Date.now();
  // Notify the new subscriber so it can anchor against the current time
  // rather than a stale module-level snapshot from previous activity.
  listener();
  return () => {
    liveTickListeners.delete(listener);
    if (liveTickListeners.size === 0 && liveTickInterval !== null) {
      clearInterval(liveTickInterval);
      liveTickInterval = null;
    }
  };
}

function useLiveNowMs(active: boolean): number {
  const subscribe = useCallback(
    (listener: () => void) => (active ? subscribeLiveTick(listener) : () => {}),
    [active],
  );
  const getSnapshot = useCallback(() => liveTickNowMs, []);
  const getServerSnapshot = useCallback(() => 0, []);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

function useLiveTurnElapsedSeconds(
  reportedSeconds: number | null | undefined,
  active: boolean,
): number | null {
  const hasReported = typeof reportedSeconds === "number"
    && Number.isFinite(reportedSeconds);
  const reportedValue = hasReported ? reportedSeconds : 0;
  const subscribed = active && hasReported;
  const nowMs = useLiveNowMs(subscribed);
  const anchorRef = useRef<{
    reportedValue: number;
    subscribed: boolean;
    anchorMs: number;
  } | null>(null);
  anchorRef.current ??= {
    reportedValue,
    subscribed: false,
    anchorMs: Date.now(),
  };

  // Re-anchor when:
  // - the reported value changes (a new turn_usage update arrived),
  // - subscription toggles,
  // - the live clock jumps backwards.
  let anchor = anchorRef.current;
  const subscriptionJustStarted = subscribed && !anchor.subscribed;
  const clockJumpedBackwards = subscribed && nowMs < anchor.anchorMs;
  const shouldResetAnchor =
    anchor.reportedValue !== reportedValue
    || anchor.subscribed !== subscribed
    || subscriptionJustStarted
    || clockJumpedBackwards;
  if (shouldResetAnchor) {
    anchor = {
      reportedValue,
      subscribed,
      anchorMs: Date.now(),
    };
    anchorRef.current = anchor;
  }

  if (!hasReported) return null;
  if (!active) return reportedValue;
  if (!subscribed || nowMs <= anchor.anchorMs) {
    return reportedValue;
  }
  const elapsed = (nowMs - anchor.anchorMs) / 1000;
  return Math.max(0, reportedValue + elapsed);
}

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
      item.createdAt ?? "",
      item.updatedAt ?? "",
      item.role,
      item.content,
      item.filePaths?.join("\0") ?? "",
      item.imageAttachments?.map((attachment) => attachment.upload_id).join("\0") ?? "",
    ].join("\0");
  }
  if (item.kind === "thinking") {
    return [
      item.kind,
      item.itemId,
      item.createdAt ?? "",
      item.updatedAt ?? "",
      item.title,
      item.content,
    ].join("\0");
  }
  return [
    item.kind,
    item.itemId,
    item.createdAt ?? "",
    item.updatedAt ?? "",
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

function timestampMs(value: string | undefined): number | null {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isNaN(time) ? null : time;
}

function secondsBetween(start: number | null, end: number | null): number | null {
  if (start === null || end === null || end <= start) return null;
  return (end - start) / 1000;
}

function timelineItemsRangeMs(items: readonly TimelineItem[]): { start: number | null; end: number | null } {
  let start: number | null = null;
  let end: number | null = null;

  for (const item of items) {
    const itemStart = timestampMs(item.createdAt) ?? timestampMs(item.updatedAt);
    const itemEnd = timestampMs(item.updatedAt) ?? timestampMs(item.createdAt);
    if (itemStart !== null) {
      start = start === null ? itemStart : Math.min(start, itemStart);
    }
    if (itemEnd !== null) {
      end = end === null ? itemEnd : Math.max(end, itemEnd);
    }
  }

  return { start, end };
}

function timelineItemsDurationSeconds(items: readonly TimelineItem[]): number | null {
  const range = timelineItemsRangeMs(items);
  return secondsBetween(range.start, range.end);
}

function messageStartMs(item: TimelineMessageItem): number | null {
  return timestampMs(item.createdAt) ?? timestampMs(item.updatedAt);
}

function messageEndMs(item: TimelineMessageItem): number | null {
  return timestampMs(item.updatedAt) ?? timestampMs(item.createdAt);
}

function renderUnitKey(unit: RenderUnit): string {
  return unit.kind === "message" ? unit.item.itemId : unit.key;
}

function renderUnitStartMs(unit: RenderUnit): number | null {
  if (unit.kind === "message") return messageStartMs(unit.item);
  return timelineItemsRangeMs(unit.items).start;
}

function renderUnitEndMs(unit: RenderUnit): number | null {
  if (unit.kind === "message") return messageEndMs(unit.item);
  return timelineItemsRangeMs(unit.items).end;
}

function previousMessageEndMs(renderUnits: readonly RenderUnit[], index: number): number | null {
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const unit = renderUnits[cursor];
    if (unit.kind !== "message") continue;
    return messageEndMs(unit.item);
  }
  return null;
}

function nextNonUserMessageStartMs(renderUnits: readonly RenderUnit[], index: number): number | null {
  for (let cursor = index + 1; cursor < renderUnits.length; cursor += 1) {
    const unit = renderUnits[cursor];
    if (unit.kind !== "message") continue;
    if (unit.item.role === "user") return null;
    return messageStartMs(unit.item);
  }
  return null;
}

function workRunContextDurationSeconds(
  renderUnits: readonly RenderUnit[],
  index: number,
): number | null {
  const unit = renderUnits[index];
  if (unit?.kind !== "work_run") return null;
  const explicitDuration = timelineItemsDurationSeconds(unit.items);
  if (explicitDuration !== null) return explicitDuration;

  const range = timelineItemsRangeMs(unit.items);
  const previousMessageEnd = previousMessageEndMs(renderUnits, index);
  const nextMessageStart = nextNonUserMessageStartMs(renderUnits, index);

  if (range.start !== null || range.end !== null) {
    return secondsBetween(previousMessageEnd, range.end)
      ?? secondsBetween(range.start, nextMessageStart)
      ?? secondsBetween(previousMessageEnd, nextMessageStart);
  }

  return secondsBetween(previousMessageEnd, nextMessageStart);
}

function activeWorkRunContextDurationSeconds(
  renderUnits: readonly RenderUnit[],
  index: number,
  nowMs: number,
): number | null {
  const unit = renderUnits[index];
  if (unit?.kind !== "work_run" || unit.items.length === 0) return null;
  const range = timelineItemsRangeMs(unit.items);
  const previousMessageEnd = previousMessageEndMs(renderUnits, index);
  const start = range.start ?? previousMessageEnd;
  if (start !== null && nowMs > start) return (nowMs - start) / 1000;
  return workRunContextDurationSeconds(renderUnits, index);
}

function maxDurationSeconds(values: readonly (number | null | undefined)[]): number | null {
  let result: number | null = null;
  for (const value of values) {
    if (typeof value !== "number" || !Number.isFinite(value)) continue;
    result = result === null ? value : Math.max(result, value);
  }
  return result;
}

function buildWorkRunDurationMap(
  renderUnits: readonly RenderUnit[],
  {
    activeWorkRunKey,
    latestWorkRunKey,
    sessionIsActive,
    turnElapsedSeconds,
    activeNowMs,
  }: {
    activeWorkRunKey: string | null;
    latestWorkRunKey: string | null;
    sessionIsActive: boolean;
    turnElapsedSeconds?: number | null;
    activeNowMs?: number | null;
  },
): Map<string, number | null> {
  const durations = new Map<string, number | null>();
  renderUnits.forEach((unit, index) => {
    if (unit.kind !== "work_run") return;
    if (unit.key === activeWorkRunKey) {
      const timestampLiveDuration = typeof activeNowMs === "number"
        ? activeWorkRunContextDurationSeconds(renderUnits, index, activeNowMs)
        : null;
      durations.set(
        unit.key,
        maxDurationSeconds([turnElapsedSeconds, timestampLiveDuration])
          ?? workRunContextDurationSeconds(renderUnits, index)
          ?? null,
      );
      return;
    }

    const useTurnDurationFallback = !sessionIsActive && unit.key === latestWorkRunKey;
    durations.set(
      unit.key,
      workRunContextDurationSeconds(renderUnits, index)
        ?? (useTurnDurationFallback ? turnElapsedSeconds ?? null : null),
    );
  });
  return durations;
}

function finalTurnStartIndex(renderUnits: readonly RenderUnit[]): number {
  for (let index = renderUnits.length - 1; index >= 0; index -= 1) {
    const unit = renderUnits[index];
    if (unit?.kind === "message" && unit.item.role === "user") return index;
  }
  return 0;
}

function workRunBelongsToFinalTurn(renderUnits: readonly RenderUnit[], index: number): boolean {
  return index >= finalTurnStartIndex(renderUnits);
}

function buildWorkRunCostMap(
  renderUnits: readonly RenderUnit[],
  {
    activeWorkRunKey,
    latestWorkRunKey,
    sessionIsActive,
    turnCostUsd,
  }: {
    activeWorkRunKey: string | null;
    latestWorkRunKey: string | null;
    sessionIsActive: boolean;
    turnCostUsd?: number | null;
  },
): Map<string, number | null> {
  const costs = new Map<string, number | null>();
  renderUnits.forEach((unit, index) => {
    if (unit.kind !== "work_run") return;
    const useTurnCost = unit.key === activeWorkRunKey
      || (
        !sessionIsActive
        && unit.key === latestWorkRunKey
        && workRunBelongsToFinalTurn(renderUnits, index)
      );
    costs.set(unit.key, useTurnCost ? turnCostUsd ?? null : null);
  });
  return costs;
}

function mergeRangeStart(current: number | null, next: number | null): number | null {
  if (next === null) return current;
  return current === null ? next : Math.min(current, next);
}

function mergeRangeEnd(current: number | null, next: number | null): number | null {
  if (next === null) return current;
  return current === null ? next : Math.max(current, next);
}

function buildTurnSummaries(
  renderUnits: readonly RenderUnit[],
  {
    showSubAgentCards,
    sessionIsActive,
    turnElapsedSeconds,
    turnCostUsd,
    workRunDurations,
  }: {
    showSubAgentCards: boolean;
    sessionIsActive: boolean;
    turnElapsedSeconds?: number | null;
    turnCostUsd?: number | null;
    workRunDurations: ReadonlyMap<string, number | null>;
  },
): Map<string, TurnSummary> {
  const summaries = new Map<string, TurnSummary>();
  let turn:
    | {
      key: string;
      startMs: number | null;
      endMs: number | null;
      workItems: WorkItem[];
      workDurationSeconds: number;
      hasWorkDuration: boolean;
      lastUnitKey: string;
    }
    | null = null;

  const closeTurn = (finalTurn: boolean) => {
    if (!turn) return;
    const closedTurn = turn;
    turn = null;
    if (finalTurn && sessionIsActive) return;

    const summaryItems = workRunCountItems(closedTurn.workItems, showSubAgentCards);
    const durationSeconds = secondsBetween(closedTurn.startMs, closedTurn.endMs)
      ?? (closedTurn.hasWorkDuration ? closedTurn.workDurationSeconds : null)
      ?? (finalTurn && !sessionIsActive ? turnElapsedSeconds ?? null : null);
    const costUsd = finalTurn && !sessionIsActive ? turnCostUsd ?? null : null;
    if (!workingSummaryText(summaryItems, durationSeconds, costUsd)) return;

    summaries.set(closedTurn.lastUnitKey, {
      key: `turn-summary-${closedTurn.key}`,
      items: summaryItems,
      durationSeconds,
      costUsd,
    });
  };

  const ensureTurn = (unit: RenderUnit) => {
    if (turn) return;
    const key = renderUnitKey(unit);
    turn = {
      key,
      startMs: renderUnitStartMs(unit),
      endMs: renderUnitEndMs(unit),
      workItems: [],
      workDurationSeconds: 0,
      hasWorkDuration: false,
      lastUnitKey: key,
    };
  };

  for (const unit of renderUnits) {
    const unitKey = renderUnitKey(unit);
    if (unit.kind === "message" && unit.item.role === "user") {
      closeTurn(false);
      const timestamp = messageStartMs(unit.item);
      turn = {
        key: unit.item.itemId,
        startMs: timestamp,
        endMs: timestamp,
        workItems: [],
        workDurationSeconds: 0,
        hasWorkDuration: false,
        lastUnitKey: unitKey,
      };
      continue;
    }

    ensureTurn(unit);
    if (!turn) continue;
    if (unit.kind === "message") {
      turn.endMs = mergeRangeEnd(turn.endMs, messageEndMs(unit.item));
      turn.lastUnitKey = unitKey;
      continue;
    }

    const range = timelineItemsRangeMs(unit.items);
    turn.startMs = mergeRangeStart(turn.startMs, range.start);
    turn.endMs = mergeRangeEnd(turn.endMs, range.end);
    turn.workItems = [...turn.workItems, ...unit.items];
    const durationSeconds = workRunDurations.get(unit.key);
    if (typeof durationSeconds === "number" && Number.isFinite(durationSeconds)) {
      turn.workDurationSeconds += durationSeconds;
      turn.hasWorkDuration = true;
    }
    turn.lastUnitKey = unitKey;
  }
  closeTurn(true);
  return summaries;
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
  subAgentItems,
  parentSessionId,
}: {
  group: Extract<WorkingGroup, { kind: "sub_agent" }>;
  subAgents: Record<string, SubAgentSummary>;
  subAgentItems: WorkItem[];
  parentSessionId?: string;
}) {
  const navigate = useNavigate();
  const agent = subAgents[group.subAgentId];
  const status = agent?.status ?? (group.running ? "running" : "completed");
  const name = subAgentDisplayName(agent?.title, group.subAgentId);
  const statusModifier = subAgentStatusModifier(status);
  const subAgentIsActive = status === "running" || status === "starting";
  const summaryItems = useMemo(() => workRunCountItems(subAgentItems, false), [subAgentItems]);
  const reportedDurationSeconds = useMemo(
    () => timelineItemsDurationSeconds(subAgentItems)
      ?? agent?.turnElapsedSeconds
      ?? null,
    [agent?.turnElapsedSeconds, subAgentItems],
  );
  const summaryDurationSeconds = useLiveTurnElapsedSeconds(
    reportedDurationSeconds,
    subAgentIsActive,
  );
  const summaryCostUsd = agent?.turnCostUsd ?? null;
  const summaryText = useMemo(
    () => workingSummaryText(summaryItems, summaryDurationSeconds, summaryCostUsd),
    [summaryCostUsd, summaryDurationSeconds, summaryItems],
  );
  const ariaDetail = [summaryText, status].filter(Boolean).join(", ");
  return (
    <button
      type="button"
      className="working-items__sub-agent-card"
      aria-label={`Open ${name} agent session${ariaDetail ? `, ${ariaDetail}` : ""}`}
      onClick={() => {
        if (parentSessionId) {
          void navigate(`/sessions/${encodeURIComponent(parentSessionId)}/sub-agents/${encodeURIComponent(group.subAgentId)}`);
        }
      }}
      disabled={!parentSessionId}
    >
      <BotIcon aria-hidden="true" />
      <span className="working-items__sub-agent-content">
        <span className="working-items__sub-agent-main">{name}</span>
        <WorkingSummary
          items={summaryItems}
          durationSeconds={summaryDurationSeconds}
          costUsd={summaryCostUsd}
          className="working-items__summary working-items__sub-agent-summary"
        />
      </span>
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
  subAgentItems,
  closeSignal,
  parentSessionId,
  showSubAgentCards = true,
  fullExpanded = false,
}: {
  items: WorkItem[];
  subAgents: Record<string, SubAgentSummary>;
  subAgentItems: Record<string, WorkItem[]>;
  closeSignal: string | null;
  parentSessionId?: string;
  showSubAgentCards?: boolean;
  fullExpanded?: boolean;
}) {
  const groups = useMemo(() => buildWorkingGroups(items, showSubAgentCards), [items, showSubAgentCards]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const groupRefs = useRef(new Map<string, HTMLDivElement>());
  const lastAutoScrolledGroupKeyRef = useRef<string | null>(null);
  const needsScroll = groups.length > WORKING_ITEMS_MAX_VISIBLE;
  const [dynamicMaxHeight, setDynamicMaxHeight] = useState<number | null>(null);
  // Single open value: opening one item automatically closes any other,
  // courtesy of the Radix Accordion type="single" semantics.
  const [openValueState, setOpenValueState] = useState<{
    closeSignal: string | null;
    value: string;
  }>({ closeSignal, value: "" });
  const openValue = openValueState.closeSignal === closeSignal
    ? openValueState.value
    : "";

  const lastGroupKey = groups.at(-1)?.key ?? null;
  const hasOpenItem = openValue !== "";

  const scheduleScrollToLatestGroup = useCallback(() => {
    if (!needsScroll || fullExpanded || !lastGroupKey) return;
    if (lastAutoScrolledGroupKeyRef.current === lastGroupKey) return;
    lastAutoScrolledGroupKeyRef.current = lastGroupKey;
    requestAnimationFrame(() => {
      const scrollEl = scrollRef.current;
      if (!scrollEl) return;
      scrollEl.scrollTop = scrollEl.scrollHeight;
    });
  }, [fullExpanded, lastGroupKey, needsScroll]);

  const setScrollRef = useCallback((node: HTMLDivElement | null) => {
    scrollRef.current = node;
    if (node) scheduleScrollToLatestGroup();
  }, [scheduleScrollToLatestGroup]);

  // Stable ref-bridge so the ResizeObserver callback (created once per group node)
  // always reads the current measurement function without resubscribing.
  const syncDynamicMaxHeightRef = useRef<(preferredKey?: string) => void>(() => {});

  const setGroupRef = useCallback((key: string) => (node: HTMLDivElement | null): (() => void) | void => {
    if (!node) {
      groupRefs.current.delete(key);
      return;
    }
    groupRefs.current.set(key, node);
    if (key === lastGroupKey) scheduleScrollToLatestGroup();

    // React 19 ref-callback cleanup — no useEffect needed.
    // Observe size changes so async-rendered tool content (Shiki, markdown,
    // images) re-trigger height measurement once layout settles.
    if (typeof ResizeObserver === "undefined") {
      return () => {
        groupRefs.current.delete(key);
      };
    }
    const observer = new ResizeObserver(() => {
      syncDynamicMaxHeightRef.current(key);
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
      groupRefs.current.delete(key);
    };
  }, [lastGroupKey, scheduleScrollToLatestGroup]);

  const syncDynamicMaxHeight = useCallback((preferredKey?: string) => {
    if (!needsScroll || fullExpanded) {
      setDynamicMaxHeight((current) => (current === null ? current : null));
      return;
    }
    const scrollEl = scrollRef.current;
    if (!scrollEl) return;

    // Use scrollHeight directly: closed Collapsibles unmount their content
    // (Presence pattern), so the group's scrollHeight is naturally small when
    // closed and equals the trigger + natural content height when open.
    // The ResizeObserver attached in setGroupRef keeps this in sync as
    // async-rendered content (markdown, syntax highlighting, images) settles.
    const preferredGroup = preferredKey ? groupRefs.current.get(preferredKey) : null;
    let tallestOpenGroup = preferredGroup?.scrollHeight ?? 0;
    for (const groupEl of groupRefs.current.values()) {
      const openContent = groupEl.querySelector('[data-slot="accordion-content"][data-state="open"]');
      if (!openContent) continue;
      tallestOpenGroup = Math.max(tallestOpenGroup, groupEl.scrollHeight);
    }

    if (tallestOpenGroup === 0) {
      setDynamicMaxHeight((current) => (current === null ? current : null));
      return;
    }

    const viewportCap = typeof window !== "undefined"
      ? Math.floor(window.innerHeight * WORKING_ITEMS_OPEN_MAX_VH)
      : Number.POSITIVE_INFINITY;
    const desired = Math.ceil(tallestOpenGroup + WORKING_ITEMS_OPEN_GUTTER_PX);
    const capped = Math.min(desired, viewportCap);
    setDynamicMaxHeight((current) => {
      // Initial growth: only set when the natural height exceeds the default
      // scroll constraint.  Once grown, only allow further growth so async
      // content settling doesn't visually pop the panel smaller mid-load.
      if (current === null) return capped > scrollEl.clientHeight ? capped : null;
      return Math.max(current, capped);
    });
  }, [fullExpanded, needsScroll]);

  // "Latest ref" pattern: keep ResizeObserver callbacks pointing at the
  // current syncDynamicMaxHeight without resubscribing on every render.
  useEffect(() => {
    syncDynamicMaxHeightRef.current = syncDynamicMaxHeight;
  }, [syncDynamicMaxHeight]);

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
      syncDynamicMaxHeight(key);
      requestAnimationFrame(() => scrollGroupToCenter(key));
    });
  }, [scrollGroupToCenter, syncDynamicMaxHeight]);

  const panelStyle = needsScroll && !fullExpanded && hasOpenItem && dynamicMaxHeight !== null
    ? { "--working-items-max-height": `${dynamicMaxHeight}px` } as CSSProperties
    : undefined;

  const handleAccordionValueChange = useCallback((nextValue: string) => {
    setOpenValueState({ closeSignal, value: nextValue });
    if (nextValue) scheduleScrollGroupToCenter(nextValue);
  }, [closeSignal, scheduleScrollGroupToCenter]);

  return (
    <div
      className={`working-items${needsScroll ? " working-items--scrollable" : ""}${fullExpanded ? " working-items--fully-expanded" : ""}`}
      ref={setScrollRef}
      style={panelStyle}
    >
      <Accordion
        type="single"
        collapsible
        value={openValue}
        onValueChange={handleAccordionValueChange}
        className="working-items__accordion"
      >
        {groups.map((group) => {
          if (group.kind === "sub_agent") {
            return (
              <div key={group.key} ref={setGroupRef(group.key)} className="working-items__item">
                <SubAgentCard
                  group={group}
                  subAgents={subAgents}
                  subAgentItems={subAgentItems[group.subAgentId] ?? group.items}
                  parentSessionId={parentSessionId}
                />
              </div>
            );
          }
          if (group.kind === "tool") {
            const entry = group.entry;
            return (
              <AccordionItem
                key={group.key}
                value={group.key}
                ref={setGroupRef(group.key)}
                className="working-items__item working-items__accordion-item"
              >
                <AccordionPrimitive.Header className="working-items__accordion-header">
                  <AccordionPrimitive.Trigger asChild>
                    <Button type="button" variant="ghost" size="sm" className="working-items__tool-trigger" data-timeline-item-id={entry.itemId}>
                      <ChevronRightIcon className="timeline-entry__chevron" />
                      <span className="working-items__tool-title">{entry.displayLabel}</span>
                      <span className="working-items__tool-subtitle">{toolSubtitle(entry)}</span>
                      {entry.status === "running" ? <span className="timeline-entry__running" aria-label="running" /> : null}
                    </Button>
                  </AccordionPrimitive.Trigger>
                </AccordionPrimitive.Header>
                <AccordionPrimitive.Content
                  data-slot="accordion-content"
                  className="working-items__accordion-content"
                >
                  <div className="working-items__tool-detail">
                    <ToolResult
                      metadata={entry.entry.metadata}
                      text={entry.entry.text}
                      running={entry.status === "running"}
                    />
                  </div>
                </AccordionPrimitive.Content>
              </AccordionItem>
            );
          }
          const groupLabel = "Thinking";
          return (
            <AccordionItem
              key={group.key}
              value={group.key}
              ref={setGroupRef(group.key)}
              className="working-items__item working-items__accordion-item"
            >
              <AccordionPrimitive.Header className="working-items__accordion-header">
                <AccordionPrimitive.Trigger asChild>
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
                </AccordionPrimitive.Trigger>
              </AccordionPrimitive.Header>
              <AccordionPrimitive.Content
                data-slot="accordion-content"
                className="working-items__accordion-content"
              >
                {group.items.map((item) => (
                  <div key={item.itemId} className="working-items__thinking-detail" data-timeline-item-id={item.itemId}>
                    <MarkdownContent content={item.content} />
                  </div>
                ))}
              </AccordionPrimitive.Content>
            </AccordionItem>
          );
        })}
      </Accordion>
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

function waitForNextAnimationFrame(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve());
  });
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
  open,
  closeSignal,
  onOpenChange,
  onUserOpen,
  parentSessionId,
  showSubAgentCards,
  durationSeconds,
  costUsd,
  subAgentItems,
}: {
  unit: Extract<RenderUnit, { kind: "work_run" }>;
  subAgents: Record<string, SubAgentSummary>;
  active: boolean;
  phase: WorkRunPhase | null;
  open: boolean;
  closeSignal: string | null;
  onOpenChange: (nextOpen: boolean) => void;
  onUserOpen?: (contentEl: HTMLElement | null) => void;
  parentSessionId?: string;
  showSubAgentCards?: boolean;
  durationSeconds?: number | null;
  costUsd?: number | null;
  subAgentItems: Record<string, WorkItem[]>;
}) {
  const hasItems = unit.items.length > 0;
  const lastItemId = hasItems ? unit.items[unit.items.length - 1].itemId : undefined;
  const [fullExpandedState, setFullExpandedState] = useState({
    expanded: false,
    closeSignal,
  });
  const rawFullExpanded = fullExpandedState.closeSignal === closeSignal
    ? fullExpandedState.expanded
    : false;
  const contentRef = useRef<HTMLDivElement>(null);
  const workRunSummaryItems = useMemo(
    () => workRunCountItems(unit.items, showSubAgentCards ?? true),
    [showSubAgentCards, unit.items],
  );
  const workRunSummary = useMemo(
    () => workingSummaryText(workRunSummaryItems, durationSeconds, costUsd),
    [costUsd, durationSeconds, workRunSummaryItems],
  );
  const hasRunningSubAgent = useMemo(
    () => unit.items.some((item) => {
      if (!item.subAgentId) return false;
      const status = subAgents[item.subAgentId]?.status;
      return status === "running" || status === "starting";
    }),
    [subAgents, unit.items],
  );
  const hasVisibleSummary = workRunSummary.length > 0;
  const isVisiblyActive = active || unit.running || hasRunningSubAgent;
  const showPlaceholderSummary = active && !hasVisibleSummary;
  const workRunGroupCount = useMemo(
    () => buildWorkingGroups(unit.items, showSubAgentCards ?? true).length,
    [showSubAgentCards, unit.items],
  );
  const canFullExpand = workRunGroupCount > WORKING_ITEMS_MAX_VISIBLE;
  const fullExpanded = canFullExpand && rawFullExpanded;
  const pendingUserOpenScrollRef = useRef(false);

  const setOpenFromUser = useCallback((nextOpen: boolean) => {
    pendingUserOpenScrollRef.current = nextOpen;
    onOpenChange(nextOpen);
  }, [onOpenChange]);

  const toggleFullExpanded = useCallback(() => {
    if (!canFullExpand) return;
    pendingUserOpenScrollRef.current = true;
    onOpenChange(true);
    setFullExpandedState((current) => ({
      closeSignal,
      expanded: current.closeSignal === closeSignal ? !current.expanded : true,
    }));
  }, [canFullExpand, closeSignal, onOpenChange]);

  useLayoutEffect(() => {
    if (!open || !pendingUserOpenScrollRef.current) return;
    const contentEl = contentRef.current;
    if (!contentEl) return;
    // The first open mounts CollapsibleContent after the click handler, so
    // wait until the committed layout before measuring and aligning it.
    pendingUserOpenScrollRef.current = false;
    onUserOpen?.(contentEl);
  });

  const handleWorkRunHeaderKeyDown = useCallback((event: KeyboardEvent<HTMLButtonElement>) => {
    if (!canFullExpand || !event.altKey || event.key !== "Enter") return;
    event.preventDefault();
    event.stopPropagation();
    toggleFullExpanded();
  }, [canFullExpand, toggleFullExpanded]);

  const handleWorkRunHeaderClickCapture = useCallback((event: MouseEvent<HTMLButtonElement>) => {
    if (!canFullExpand || !event.altKey) return;
    event.preventDefault();
    event.stopPropagation();
    toggleFullExpanded();
  }, [canFullExpand, toggleFullExpanded]);

  return (
    <div
      className="timeline-entry timeline-entry--work-run"
      data-timeline-item-id={lastItemId}
    >
      <Collapsible
        open={open}
        onOpenChange={setOpenFromUser}
      >
        <div className="timeline-entry__work-run-header-row">
          <CollapsibleTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="timeline-entry__header timeline-entry__header--work-run"
              data-phase={phase ?? undefined}
              aria-label={workRunSummary ? `Working ${workRunSummary}` : "Working"}
              aria-keyshortcuts={canFullExpand ? "Alt+Enter" : undefined}
              title={canFullExpand ? "Click to expand. Alt-click or Alt+Enter fully expands the tool list." : undefined}
              onClickCapture={handleWorkRunHeaderClickCapture}
              onKeyDown={handleWorkRunHeaderKeyDown}
            >
              <ChevronRightIcon className="timeline-entry__chevron" />
              <TextShimmer text="Working" active={isVisiblyActive} className="timeline-entry__working-label" />
              <WorkingSummary
                items={workRunSummaryItems}
                durationSeconds={durationSeconds}
                costUsd={costUsd}
                placeholder={showPlaceholderSummary ? "Preparing…" : null}
                className={
                  showPlaceholderSummary
                    ? "working-items__summary working-items__summary--placeholder"
                    : "working-items__summary"
                }
              />
            </Button>
          </CollapsibleTrigger>
        </div>
        {hasItems ? (
          <CollapsibleContent>
            <div className="timeline-entry__work-run-body" ref={contentRef}>
              <WorkingItemsPanel
                items={unit.items}
                subAgents={subAgents}
                closeSignal={closeSignal}
                parentSessionId={parentSessionId}
                showSubAgentCards={showSubAgentCards}
                fullExpanded={fullExpanded}
                subAgentItems={subAgentItems}
              />
              {canFullExpand ? (
                <button
                  type="button"
                  className="working-items__more-toggle"
                  aria-label={fullExpanded ? "Limit Working tool list to five rows" : "Fully expand Working tool list"}
                  aria-pressed={fullExpanded}
                  aria-keyshortcuts="Alt+Enter"
                  onClick={toggleFullExpanded}
                >
                  {fullExpanded ? (
                    <>
                      <ChevronUpIcon className="working-items__more-toggle-icon" />
                      <span className="working-items__more-toggle-label">
                        Show recent {WORKING_ITEMS_MAX_VISIBLE}
                      </span>
                    </>
                  ) : (
                    <>
                      <ChevronDownIcon className="working-items__more-toggle-icon" />
                      <span className="working-items__more-toggle-label">
                        +{Math.max(0, workRunGroupCount - WORKING_ITEMS_MAX_VISIBLE)} more
                      </span>
                    </>
                  )}
                </button>
              ) : null}
            </div>
          </CollapsibleContent>
        ) : null}
      </Collapsible>
    </div>
  );
}

function TurnSummaryBlock({
  items,
  durationSeconds,
  costUsd,
}: {
  items: CountSummaryItem[];
  durationSeconds?: number | null;
  costUsd?: number | null;
}) {
  const summaryText = workingSummaryText(items, durationSeconds, costUsd);
  if (!summaryText) return null;

  return (
    <div
      className="timeline-entry timeline-entry--turn-summary"
      role="note"
      aria-label={`Turn summary ${summaryText}`}
    >
      <div className="timeline-entry__turn-summary-divider">
        <span className="timeline-entry__turn-summary-rule" aria-hidden="true" />
        <span className="timeline-entry__turn-summary-card">
          <CheckIcon
            className="timeline-entry__turn-summary-icon"
            aria-hidden="true"
          />
          <WorkingSummary
            items={items}
            durationSeconds={durationSeconds}
            costUsd={costUsd}
            className="working-items__summary timeline-entry__turn-summary-summary"
          />
        </span>
        <span className="timeline-entry__turn-summary-rule" aria-hidden="true" />
      </div>
    </div>
  );
}

type SessionTimelineProps = {
  items: TimelineItem[];
  subAgents: Record<string, SubAgentSummary>;
  subAgentItems?: Record<string, TimelineItem[]>;
  turnElapsedSeconds?: number | null;
  turnCostUsd?: number | null;
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
  left: Record<string, SubAgentSummary>,
  right: Record<string, SubAgentSummary>,
): boolean {
  const leftEntries = Object.entries(left);
  const rightEntries = Object.entries(right);
  if (leftEntries.length !== rightEntries.length) return false;
  return leftEntries.every(([subAgentId, leftSubAgent]) => {
    const rightSubAgent = right[subAgentId];
    return rightSubAgent !== undefined
      && leftSubAgent.title === rightSubAgent.title
      && leftSubAgent.status === rightSubAgent.status
      && (leftSubAgent.turnElapsedSeconds ?? null) === (rightSubAgent.turnElapsedSeconds ?? null)
      && (leftSubAgent.turnCostUsd ?? null) === (rightSubAgent.turnCostUsd ?? null);
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
    && previous.turnElapsedSeconds === next.turnElapsedSeconds
    && previous.turnCostUsd === next.turnCostUsd
    && previous.subAgentItems === next.subAgentItems
    && previous.onForkMessage === next.onForkMessage
    && subAgentSummariesEqual(previous.subAgents, next.subAgents);
}

export const SessionTimeline = memo(function SessionTimeline({
  items,
  subAgents,
  subAgentItems = {},
  turnElapsedSeconds,
  turnCostUsd,
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
  const scrollRequestRef = useRef(0);
  const [openWorkRunState, setOpenWorkRunState] = useState<{
    key: string | null;
    closeSignal: string | null;
  }>({
    key: null,
    closeSignal: null,
  });
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
  const latestWorkRunKey = [...renderUnits].reverse().find((unit) => unit.kind === "work_run")?.key ?? null;
  const liveTurnElapsedSeconds = useLiveTurnElapsedSeconds(
    turnElapsedSeconds ?? null,
    sessionIsActive,
  );
  const activeTimestampNowMs = useLiveNowMs(
    sessionIsActive
      && activeWorkRunKey !== null,
  );
  const workRunDurations = useMemo(
    () => buildWorkRunDurationMap(renderUnits, {
      activeWorkRunKey,
      latestWorkRunKey,
      sessionIsActive,
      turnElapsedSeconds: liveTurnElapsedSeconds,
      activeNowMs: activeTimestampNowMs,
    }),
    [activeTimestampNowMs, activeWorkRunKey, latestWorkRunKey, renderUnits, sessionIsActive, liveTurnElapsedSeconds],
  );
  const workRunCosts = useMemo(
    () => buildWorkRunCostMap(renderUnits, {
      activeWorkRunKey,
      latestWorkRunKey,
      sessionIsActive,
      turnCostUsd,
    }),
    [activeWorkRunKey, latestWorkRunKey, renderUnits, sessionIsActive, turnCostUsd],
  );
  const turnSummaries = useMemo(
    () => buildTurnSummaries(renderUnits, {
      showSubAgentCards,
      sessionIsActive,
      turnElapsedSeconds: liveTurnElapsedSeconds,
      turnCostUsd,
      workRunDurations,
    }),
    [
      renderUnits,
      sessionIsActive,
      showSubAgentCards,
      liveTurnElapsedSeconds,
      turnCostUsd,
      workRunDurations,
    ],
  );
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
  const openWorkRunKey = openWorkRunState.closeSignal === closeCollapsiblesSignal
    ? openWorkRunState.key
    : null;

  const setWorkRunOpen = useCallback((unitKey: string, nextOpen: boolean) => {
    setOpenWorkRunState((current) => {
      if (nextOpen) {
        return { key: unitKey, closeSignal: closeCollapsiblesSignal };
      }
      if (
        current.closeSignal !== closeCollapsiblesSignal
        || current.key !== unitKey
      ) {
        return current;
      }
      return { key: null, closeSignal: closeCollapsiblesSignal };
    });
  }, [closeCollapsiblesSignal]);

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

  const scrollToTargetBottom = useCallback(
    (container: HTMLElement, target: HTMLElement) => {
      if (!container.isConnected || !target.isConnected) return;
      const containerRect = container.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const delta = targetRect.bottom - containerRect.bottom;
      const maxScrollTop = Math.max(0, container.scrollHeight - container.clientHeight);
      markProgrammaticScroll();
      container.scrollTo({
        top: Math.min(Math.max(container.scrollTop + delta, 0), maxScrollTop),
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
        if (contentEl && !contentEl.isConnected) return;
        if (contentEl) {
          // Bring the bottom of the freshly expanded panel into view so the
          // latest tool output is visible without ever jumping the viewport
          // upward. Keep a small gutter so the panel does not sit underneath
          // the composer shadow/edge when it is the last conversation item.
          const containerRect = container.getBoundingClientRect();
          const contentRect = contentEl.getBoundingClientRect();
          const delta = contentRect.bottom - (
            containerRect.bottom - WORK_RUN_OPEN_BOTTOM_GUTTER_PX
          );
          if (delta > 0) {
            const maxScrollTop = Math.max(
              0,
              container.scrollHeight - container.clientHeight,
            );
            markProgrammaticScroll();
            container.scrollTo({
              top: Math.min(container.scrollTop + delta, maxScrollTop),
              behavior: "instant",
            });
          }
          return;
        }
        // Fallback: stick to the very bottom of the timeline.
        markProgrammaticScroll();
        container.scrollTo({
          top: container.scrollHeight,
          behavior: "instant",
        });
      };
      // Wait for the open content to mount and then re-check after layout has
      // settled. The first open can grow in multiple phases (Radix presence,
      // measured scroll constraints, syntax/markdown rendering), and a single
      // early frame can still see the old scrollHeight.
      requestAnimationFrame(() => {
        align();
        requestAnimationFrame(align);
      });
      window.setTimeout(align, WORK_RUN_OPEN_LAYOUT_SETTLE_MS);
      if (contentEl && typeof ResizeObserver !== "undefined") {
        const observer = new ResizeObserver(() => {
          requestAnimationFrame(align);
        });
        observer.observe(contentEl);
        window.setTimeout(() => {
          observer.disconnect();
        }, WORK_RUN_OPEN_LAYOUT_SETTLE_MS);
      }
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
    const latestUserMessageChanged =
      previousVisibleItemsChangeKey !== undefined
      && latestItemIsUserMessage
      && previousVisibleItemsChangeKey !== visibleItemsChangeKey;
    const scrollRequestId = scrollRequestRef.current + 1;

    if ((isNewItem || latestUserMessageChanged) && latestItem) {
      scrollRequestRef.current = scrollRequestId;
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
        setShowNewMessages(false);
        if (target) {
          void waitForImages(target).then(async () => {
            if (latestUserMessageHasImages) {
              // Cached images can report complete before the new attachment
              // has taken its final layout height. Give the browser one paint
              // after decode/load before anchoring the message bottom.
              await waitForNextAnimationFrame();
            }
            if (scrollRequestRef.current !== scrollRequestId) return;
            if (latestUserMessageHasImages) {
              scrollToTargetBottom(container, target);
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
            if (scrollRequestRef.current !== scrollRequestId) return;
            scrollToTarget(container, target, ASSISTANT_MESSAGE_TOP_OFFSET);
          });
        }
      } else {
        setShowNewMessages(true);
      }
    } else if (!isNewItem) {
      scrollRequestRef.current = scrollRequestId;
      // Existing item content updated — stick to bottom
      if (!userScrolledRef.current) {
        markProgrammaticScroll();
        container.scrollTo({ top: container.scrollHeight, behavior: "instant" });
      } else {
        setShowNewMessages(true);
      }
    }
  }, [containerRef, itemsVersion, latestRawItem, visibleItemsChangeKey, visibleItems.length, latestItem, latestItemIsUserMessage, latestUserMessageHasImages, userScrolledRef, setShowNewMessages, scrollToTarget, scrollToTargetBottom, markProgrammaticScroll]);

  const shouldShowNewMessages = showNewMessages && !latestItemIsUserMessage;

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
          const unitKey = renderUnitKey(unit);
          const turnSummary = turnSummaries.get(unitKey);
          const summaryNode = turnSummary ? (
            <TurnSummaryBlock
              key={turnSummary.key}
              items={turnSummary.items}
              durationSeconds={turnSummary.durationSeconds}
              costUsd={turnSummary.costUsd}
            />
          ) : null;
          if (unit.kind === "message") {
            return (
              <Fragment key={unitKey}>
                <TimelineEntry
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
                {summaryNode}
              </Fragment>
            );
          }
          const isActiveUnit = unit.key === activeWorkRunKey;
          const workRunDurationSeconds = workRunDurations.get(unit.key) ?? null;
          const workRunCostUsd = workRunCosts.get(unit.key) ?? null;
          // Only the currently active WorkRun should treat user-opens as a
          // "follow the latest output" intent. An active block can be between
          // tool phases (for example model_wait/finalizing) even when none of
          // its tool groups currently reports `running`.
          return (
            <Fragment key={unitKey}>
              <WorkRun
                unit={unit}
                subAgents={subAgents}
                active={isActiveUnit}
                phase={isActiveUnit ? visibleActivePhase : null}
                open={openWorkRunKey === unit.key}
                closeSignal={closeCollapsiblesSignal}
                onOpenChange={(nextOpen) => setWorkRunOpen(unit.key, nextOpen)}
                onUserOpen={
                  isActiveUnit ? handleUserOpenCollapsible : undefined
                }
                parentSessionId={parentSessionId}
                showSubAgentCards={showSubAgentCards}
                durationSeconds={workRunDurationSeconds}
                costUsd={workRunCostUsd}
                subAgentItems={subAgentItems}
              />
              {summaryNode}
            </Fragment>
          );
        })}
        {shouldShowNewMessages ? (
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
