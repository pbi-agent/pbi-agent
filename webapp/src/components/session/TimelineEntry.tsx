import { useState, type JSX, type ReactNode } from "react";
import { ChevronRightIcon } from "lucide-react";
import type { ImageAttachment, TimelineItem } from "../../types";
import { Button } from "../ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { MarkdownContent } from "../shared/MarkdownContent";
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
            <a
              key={attachment.upload_id}
              className="timeline-entry__attachment"
              href={attachment.preview_url}
              target="_blank"
              rel="noreferrer"
              title={attachment.name}
            >
              <img
                className="timeline-entry__attachment-preview"
                src={attachment.preview_url}
                alt={attachment.name}
              />
              <span className="timeline-entry__attachment-name">{attachment.name}</span>
            </a>
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

export function TimelineEntry({
  item,
  subAgentTitle,
  subAgentStatus,
  bare = false,
  closeSignal = null,
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

  const subAgentBanner =
    subAgentTitle || subAgentStatus ? (
      <div className="timeline-entry__subagent">
        <span className={`indicator-dot indicator-dot--${subAgentStatus === "running" ? "connecting" : "connected"}`} />
        <span>{subAgentTitle ?? "sub_agent"} &middot; {subAgentStatus ?? "running"}</span>
      </div>
    ) : null;

  if (item.kind === "message") {
    const roleClass =
      item.role === "user" ? "user"
      : item.role === "error" ? "error"
      : item.role === "notice" ? "notice"
      : item.role === "debug" ? "debug"
      : "assistant";

    return (
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
      </div>
    );
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
