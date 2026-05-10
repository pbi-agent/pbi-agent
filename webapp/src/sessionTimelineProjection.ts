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
    title: "Sub-agent",
    content: "",
    subAgentId,
  };
}

function timelineItemSignature(
  item: TimelineItem,
  options: { collapseSubAgentItems?: boolean } = {},
): TimelineItemSignature {
  const subAgentId = timelineItemSubAgentId(item);
  if (options.collapseSubAgentItems && subAgentId) {
    return ["sub-agent-card", item.itemId, subAgentId];
  }
  if (item.kind === "message") {
    return [
      item.kind,
      item.itemId,
      item.messageId ?? "",
      item.role,
      item.content,
      item.markdown ? "1" : "0",
      item.filePaths ?? [],
      item.imageAttachments?.map((attachment) => attachment.upload_id) ?? [],
    ];
  }
  if (item.kind === "thinking") {
    return [item.kind, item.itemId, item.title, item.content];
  }
  return [
    item.kind,
    item.itemId,
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
  let subAgentsInCurrentWorkRun = new Set<string>();

  for (const item of items) {
    const subAgentId = timelineItemSubAgentId(item);
    if (subAgentId) {
      if (!subAgentsInCurrentWorkRun.has(subAgentId)) {
        subAgentsInCurrentWorkRun.add(subAgentId);
        projected.push(subAgentPlaceholder(item, subAgentId));
      }
      continue;
    }

    projected.push(item);
    if (item.kind === "message") {
      subAgentsInCurrentWorkRun = new Set<string>();
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
