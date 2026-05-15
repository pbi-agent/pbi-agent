import type { TimelineItem } from "./types";

export type TimelineProjection = {
  items: TimelineItem[];
  signature: string;
};

type TimelineItemSignature = unknown[];

const SUB_AGENT_ITEM_ID_PATTERN = /^(?:(.+):)?(subagent-\d+)-/;

export function timelineItemSubAgentId(item: TimelineItem): string | undefined {
  if (item.subAgentId) return item.subAgentId;
  const match = SUB_AGENT_ITEM_ID_PATTERN.exec(item.itemId);
  if (!match) return undefined;
  const namespace = match[1];
  const localSubAgentId = match[2];
  return namespace ? `${namespace}:${localSubAgentId}` : localSubAgentId;
}

function subAgentPlaceholder(source: TimelineItem, subAgentId: string): TimelineItem {
  return {
    kind: "thinking",
    itemId: `sub-agent-card:${subAgentId}:${source.itemId}`,
    ...(source.createdAt ? { createdAt: source.createdAt } : {}),
    ...(source.updatedAt ? { updatedAt: source.updatedAt } : {}),
    title: "Sub-agent",
    content: "",
    subAgentId,
  };
}

function latestTimestamp(left: string | undefined, right: string | undefined): string | undefined {
  if (!left) return right;
  if (!right) return left;
  const leftTime = Date.parse(left);
  const rightTime = Date.parse(right);
  if (Number.isNaN(leftTime)) return right;
  if (Number.isNaN(rightTime)) return left;
  return rightTime >= leftTime ? right : left;
}

function updateSubAgentPlaceholderTiming(
  current: TimelineItem,
  source: TimelineItem,
): TimelineItem {
  const sourceEnd = source.updatedAt ?? source.createdAt;
  const updatedAt = latestTimestamp(current.updatedAt ?? current.createdAt, sourceEnd);
  return {
    ...current,
    ...(updatedAt ? { updatedAt } : {}),
  };
}

function timelineItemSignature(
  item: TimelineItem,
  options: { collapseSubAgentItems?: boolean } = {},
): TimelineItemSignature {
  const subAgentId = timelineItemSubAgentId(item);
  if (options.collapseSubAgentItems && subAgentId) {
    return [
      "sub-agent-card",
      item.itemId,
      subAgentId,
      item.createdAt ?? "",
      item.updatedAt ?? "",
    ];
  }
  if (item.kind === "message") {
    return [
      item.kind,
      item.itemId,
      item.createdAt ?? "",
      item.updatedAt ?? "",
      item.messageId ?? "",
      item.role,
      item.content,
      item.markdown ? "1" : "0",
      item.filePaths ?? [],
      item.imageAttachments?.map((attachment) => attachment.upload_id) ?? [],
      item.turnUsage ?? null,
    ];
  }
  if (item.kind === "thinking") {
    return [
      item.kind,
      item.itemId,
      item.createdAt ?? "",
      item.updatedAt ?? "",
      item.title,
      item.content,
    ];
  }
  return [
    item.kind,
    item.itemId,
    item.createdAt ?? "",
    item.updatedAt ?? "",
    item.label,
    item.status ?? "",
    item.items.map((entry) => [
      entry.text,
      entry.classes ?? "",
      entry.metadata ?? null,
    ]),
  ];
}

export function projectionSignature(
  items: TimelineItem[],
  options: { collapseSubAgentItems?: boolean } = {},
): string {
  return JSON.stringify(items.map((item) => timelineItemSignature(item, options)));
}

export function projectMainTimelineItems(items: TimelineItem[]): TimelineProjection {
  const projected: TimelineItem[] = [];
  let subAgentsInCurrentWorkRun = new Map<string, number>();

  for (const item of items) {
    const subAgentId = timelineItemSubAgentId(item);
    if (subAgentId) {
      const existingIndex = subAgentsInCurrentWorkRun.get(subAgentId);
      if (existingIndex === undefined) {
        subAgentsInCurrentWorkRun.set(subAgentId, projected.length);
        projected.push(subAgentPlaceholder(item, subAgentId));
      } else {
        projected[existingIndex] = updateSubAgentPlaceholderTiming(
          projected[existingIndex],
          item,
        );
      }
      continue;
    }

    projected.push(item);
    if (item.kind === "message") {
      subAgentsInCurrentWorkRun = new Map<string, number>();
    }
  }

  return {
    items: projected,
    signature: projectionSignature(projected, { collapseSubAgentItems: true }),
  };
}

export function projectSubAgentTimelineItems(
  items: TimelineItem[],
  subAgentId: string,
): TimelineProjection {
  const projected = items.filter((item) => timelineItemSubAgentId(item) === subAgentId);
  return {
    items: projected,
    signature: projectionSignature(projected),
  };
}
