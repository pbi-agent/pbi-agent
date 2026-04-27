import { useState, type JSX, type ReactNode } from "react";
import { ChevronRightIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ImageAttachment, TimelineItem } from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { GitDiffResult, isApplyPatchToolMetadata } from "./GitDiffResult";

function MarkdownContent({ content }: { content: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>;
}

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
}: {
  item: TimelineItem;
  subAgentTitle?: string;
  subAgentStatus?: string;
}) {
  const startsCollapsed =
    item.kind !== "tool_group"
    || !item.items.some((toolItem) => isApplyPatchToolMetadata(toolItem.metadata));
  const [collapsed, setCollapsed] = useState(startsCollapsed);

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
          onClick={() => setCollapsed((prev) => !prev)}
        >
          <ChevronRightIcon className={`timeline-entry__chevron ${collapsed ? "" : "timeline-entry__chevron--open"}`} />
          <span>{item.title}</span>
        </Button>
        {!collapsed ? (
          <div className="timeline-entry__body">
            <MarkdownContent content={item.content} />
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className="timeline-entry timeline-entry--tool"
      data-timeline-item-id={item.itemId}
    >
      {subAgentBanner}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="timeline-entry__header"
        onClick={() => setCollapsed((prev) => !prev)}
      >
        <ChevronRightIcon className={`timeline-entry__chevron ${collapsed ? "" : "timeline-entry__chevron--open"}`} />
        <span>{item.label}</span>
        {item.status === "running" ? (
          <span className="timeline-entry__running" aria-label="running" />
        ) : null}
        <Badge variant="secondary" className="timeline-entry__count">{item.items.length}</Badge>
      </Button>
      {!collapsed ? (
        <div className="timeline-entry__body">
          {item.items.map((toolItem, index) => {
            const status = toolItemStatus(toolItem);
            return isApplyPatchToolMetadata(toolItem.metadata) && status !== "running" ? (
              <GitDiffResult
                key={`${item.itemId}-${index}`}
                metadata={toolItem.metadata}
              />
            ) : (
              <pre
                key={`${item.itemId}-${index}`}
                className={`timeline-entry__tool-item${status === "running" ? " timeline-entry__tool-item--running" : ""}`}
              >
                {status === "running" ? <span className="timeline-entry__inline-spinner" /> : null}
                {toolItem.text}
              </pre>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
