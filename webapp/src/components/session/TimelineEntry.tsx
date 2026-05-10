import { useState, type JSX, type ReactNode } from "react";
import { ChevronRightIcon, SplitIcon } from "lucide-react";
import type { ImageAttachment, TimelineItem, TimelineMessageItem } from "../../types";
import { Button } from "../ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { MarkdownContent } from "../shared/MarkdownContent";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { isApplyPatchToolMetadata } from "./GitDiffResult";
import { ToolResult } from "./ToolResult";

function renderUserContent(
  content: string,
  filePaths: string[] | undefined,
  imageAttachments: ImageAttachment[] | undefined,
): JSX.Element {
  const hasText = content.trim().length > 0;
  const uniquePaths = filePaths
    ? Array.from(new Set(filePaths)).sort((left, right) => right.length - left.length)
    : [];

  const nodes: ReactNode[] = [];
  if (hasText) {
    let cursor = 0;
    let partIndex = 0;

    while (cursor < content.length) {
      let nextMatch:
        | {
            index: number;
            path: string;
          }
        | undefined;

      for (const path of uniquePaths) {
        const index = content.indexOf(path, cursor);
        if (index < 0) {
          continue;
        }
        if (
          !nextMatch ||
          index < nextMatch.index ||
          (index === nextMatch.index && path.length > nextMatch.path.length)
        ) {
          nextMatch = { index, path };
        }
      }

      if (!nextMatch) {
        nodes.push(content.slice(cursor));
        break;
      }

      if (nextMatch.index > cursor) {
        nodes.push(content.slice(cursor, nextMatch.index));
      }
      nodes.push(
        <span key={`file-tag-${partIndex}`} className="timeline-entry__file-tag">
          {nextMatch.path}
        </span>,
      );
      partIndex += 1;
      cursor = nextMatch.index + nextMatch.path.length;
    }
  }

  return (
    <>
      {imageAttachments && imageAttachments.length > 0 ? (
        <div className="timeline-entry__attachments">
          {imageAttachments.map((attachment) => (
            <Tooltip key={attachment.upload_id}>
              <TooltipTrigger asChild>
                <a
                  className="timeline-entry__attachment"
                  href={attachment.preview_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <img
                    className="timeline-entry__attachment-preview"
                    src={attachment.preview_url}
                    alt={attachment.name}
                  />
                  <span className="timeline-entry__attachment-name">{attachment.name}</span>
                </a>
              </TooltipTrigger>
              <TooltipContent>{attachment.name}</TooltipContent>
            </Tooltip>
          ))}
        </div>
      ) : null}
      {hasText ? <p className="timeline-entry__user-text">{nodes}</p> : null}
    </>
  );
}

function toolItemStatus(toolItem: { metadata?: { status?: string; success?: boolean } }): string | null {
  if (toolItem.metadata?.status) return toolItem.metadata.status;
  if (toolItem.metadata?.success === true) return "completed";
  if (toolItem.metadata?.success === false) return "failed";
  return null;
}

function subAgentHeaderName(title: string | undefined): string | undefined {
  return title?.split("·", 1)[0]?.trim() || title;
}

function isCompactionSummaryMessage(item: TimelineMessageItem): boolean {
  return item.role === "assistant"
    && item.content.trimStart().startsWith("[compacted context — reference only]");
}

export function TimelineEntry({
  item,
  subAgentTitle,
  subAgentStatus,
  bare = false,
  closeSignal = null,
  onForkMessage,
}: {
  item: TimelineItem;
  subAgentTitle?: string;
  subAgentStatus?: string;
  /**
   * When true, the entry renders without its own collapsible/header chrome.
   * Used by SessionTimeline when several tool/thinking items are coalesced
   * into a single outer Collapsible.
   */
  bare?: boolean;
  /** Session timeline signal that closes open details when the final answer arrives. */
  closeSignal?: string | null;
  onForkMessage?: (messageId: string) => void;
}) {
  const toolGroupDefaultOpen =
    item.kind === "tool_group"
    && item.status !== "running"
    && item.items.some((toolItem) => isApplyPatchToolMetadata(toolItem.metadata));
  const [thinkingCollapsedState, setThinkingCollapsedState] = useState({
    collapsed: true,
    closeSignal,
  });
  const thinkingCollapsed =
    thinkingCollapsedState.closeSignal === closeSignal
      ? thinkingCollapsedState.collapsed
      : true;
  const [toolGroupOpenState, setToolGroupOpenState] = useState({
    open: toolGroupDefaultOpen,
    closeSignal,
  });
  const toolGroupOpen =
    toolGroupOpenState.closeSignal === closeSignal
      ? toolGroupOpenState.open
      : false;

  const subAgentName = subAgentHeaderName(subAgentTitle);
  const subAgentBanner =
    subAgentName || subAgentStatus ? (
      <div className="timeline-entry__subagent">
        <span className={`indicator-dot indicator-dot--${subAgentStatus === "running" ? "connecting" : "connected"}`} />
        <span>{subAgentName ?? "sub_agent"}</span>
      </div>
    ) : null;

  if (item.kind === "message") {
    if (item.role === "assistant" && item.content.trim() === "[compacted context]") {
      return (
        <div
          className="timeline-entry timeline-entry--compaction"
          data-timeline-item-id={item.itemId}
        >
          <Separator />
          <span className="timeline-entry__compaction-label">compacted context</span>
        </div>
      );
    }

    const roleClass =
      item.role === "user" ? "user"
      : item.role === "error" ? "error"
      : item.role === "notice" ? "notice"
      : item.role === "debug" ? "debug"
      : "assistant";

    const canFork =
      onForkMessage
      && item.messageId
      && !item.subAgentId
      && item.role === "assistant";
    const forkAction = canFork ? (
      <div className="timeline-entry__fork">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              className="timeline-entry__fork-button"
              aria-label="Fork conversation"
              onClick={() => onForkMessage(item.messageId!)}
            >
              <SplitIcon className="rotate-180" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Fork conversation</TooltipContent>
        </Tooltip>
      </div>
    ) : null;

    const entry = (
      <div
        className={`timeline-entry timeline-entry--${roleClass}`}
        data-timeline-item-id={item.itemId}
      >
        {subAgentBanner}
        <div className="timeline-entry__content">
          {item.markdown && roleClass !== "user" ? (
            <MarkdownContent content={item.content} />
          ) : (
            renderUserContent(
              item.content,
              item.kind === "message" && item.role === "user"
                ? item.filePaths
                : undefined,
              item.kind === "message" && item.role === "user"
                ? item.imageAttachments
                : undefined,
            )
          )}
        </div>
        {forkAction}
      </div>
    );

    if (isCompactionSummaryMessage(item)) {
      return (
        <>
          {entry}
          <div className="timeline-entry timeline-entry--compaction-summary-end">
            <Separator />
          </div>
        </>
      );
    }

    return entry;
  }

  if (item.kind === "thinking") {
    if (bare) {
      return (
        <div
          className="timeline-entry timeline-entry--thinking timeline-entry--bare"
          data-timeline-item-id={item.itemId}
        >
          {subAgentBanner}
          <div className="timeline-entry__bare-title">{item.title}</div>
          <div className="timeline-entry__body">
            <MarkdownContent content={item.content} />
          </div>
        </div>
      );
    }

    return (
      <div
        className="timeline-entry timeline-entry--thinking"
        data-timeline-item-id={item.itemId}
      >
        {subAgentBanner}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="timeline-entry__header"
          onClick={() => setThinkingCollapsedState({
            collapsed: !thinkingCollapsed,
            closeSignal,
          })}
        >
          <ChevronRightIcon className={`timeline-entry__chevron ${thinkingCollapsed ? "" : "timeline-entry__chevron--open"}`} />
          <span>{item.title}</span>
        </Button>
        {!thinkingCollapsed ? (
          <div className="timeline-entry__body">
            <MarkdownContent content={item.content} />
          </div>
        ) : null}
      </div>
    );
  }

  // tool_group
  if (bare) {
    return (
      <div
        className="timeline-entry timeline-entry--tool timeline-entry--bare"
        data-timeline-item-id={item.itemId}
      >
        {subAgentBanner}
        <div className="timeline-entry__body">
          {item.items.map((toolItem, index) => {
            const status = toolItemStatus(toolItem);
            return (
              <ToolResult
                key={`${item.itemId}-${index}`}
                metadata={toolItem.metadata}
                text={toolItem.text}
                running={status === "running"}
              />
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div
      className="timeline-entry timeline-entry--tool"
      data-timeline-item-id={item.itemId}
    >
      {subAgentBanner}
      <Collapsible
        open={toolGroupOpen}
        onOpenChange={(nextOpen) => setToolGroupOpenState({ open: nextOpen, closeSignal })}
      >
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="timeline-entry__header"
          >
            <ChevronRightIcon className="timeline-entry__chevron" />
            <span>{item.label}</span>
            {item.status === "running" ? (
              <span className="timeline-entry__running" aria-label="running" />
            ) : null}
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="timeline-entry__body">
            {item.items.map((toolItem, index) => {
              const status = toolItemStatus(toolItem);
              return (
                <ToolResult
                  key={`${item.itemId}-${index}`}
                  metadata={toolItem.metadata}
                  text={toolItem.text}
                  running={status === "running"}
                />
              );
            })}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
