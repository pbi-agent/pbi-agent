import { useId, useState, type JSX, type ReactNode } from "react";
import { ChevronRightIcon, SplitIcon } from "lucide-react";
import type { ImageAttachment, TimelineItem, TimelineMessageItem } from "../../types";
import { Button } from "../ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { CopyShortcut } from "../shared/CopyShortcut";
import { MarkdownContent } from "../shared/MarkdownContent";
import { parseReplyMessage } from "../../lib/replySnippets";
import { ReplySnippetCard } from "./ReplySnippetCard";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { isApplyPatchToolMetadata } from "./GitDiffResult";
import { ToolResult } from "./ToolResult";
import { useSkillCatalog } from "../../hooks/useSkillCatalog";
import { Spinner } from "../ui/spinner";
import { cn } from "@/lib/utils";

type RoleClass = "user" | "error" | "notice" | "debug" | "assistant";

const ENTRY_ROLE_CLASSES: Record<RoleClass, string> = {
  user: "max-w-3/4 self-end",
  assistant: "",
  error: "",
  notice: "self-center",
  debug: "",
};

const CONTENT_ROLE_CLASSES: Record<RoleClass, string> = {
  user: "rounded-lg rounded-br-sm border border-primary/30 bg-primary/10 px-5 py-3 text-sm leading-relaxed",
  assistant:
    "overflow-x-auto rounded-lg rounded-tl-sm border border-border bg-card px-5 py-4 text-sm leading-relaxed text-card-foreground",
  error: "rounded-sm border-l-4 border-destructive bg-destructive/10 px-4 py-3 text-sm text-destructive",
  notice: "px-3 py-1 text-center text-xs text-muted-foreground",
  debug: "rounded-sm bg-muted px-3 py-2 font-mono text-xs text-muted-foreground",
};

const THINKING_BODY_CLASSES =
  "rounded-sm bg-muted/50 px-5 py-4 text-sm leading-relaxed text-muted-foreground";

const SPECIAL_TAG_BOUNDARY_PATTERN = /[\s()[\]{}'"`,;]/;
const USER_TEXT_COLLAPSE_CHARACTER_THRESHOLD = 700;
const USER_TEXT_COLLAPSE_LINE_THRESHOLD = 8;

function findSkillTag(content: string, cursor: number): { index: number; tag: string } | undefined {
  for (let index = cursor; index < content.length; index += 1) {
    if (content[index] !== "$") continue;
    const previous = index > 0 ? content[index - 1] : " ";
    if (index > 0 && !SPECIAL_TAG_BOUNDARY_PATTERN.test(previous)) continue;
    const next = content[index + 1] ?? "";
    if (next === "" || next === "(" || next === "{" || /\d/.test(next)) continue;

    let end = index + 1;
    while (end < content.length && /[A-Za-z0-9_-]/.test(content[end])) {
      end += 1;
    }
    return { index, tag: content.slice(index, end) };
  }
  return undefined;
}

function findKnownSkillTag(
  content: string,
  cursor: number,
  skillNames: Set<string>,
): { index: number; tag: string } | undefined {
  let nextCursor = cursor;
  while (nextCursor < content.length) {
    const match = findSkillTag(content, nextCursor);
    if (!match) return undefined;
    if (skillNames.has(match.tag.slice(1))) return match;
    nextCursor = match.index + match.tag.length;
  }
  return undefined;
}

function renderUserTextNodes(
  content: string,
  filePaths: string[] | undefined,
  skillNames: Set<string>,
): ReactNode[] {
  const uniquePaths = filePaths
    ? Array.from(new Set(filePaths)).sort((left, right) => right.length - left.length)
    : [];
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let partIndex = 0;

  while (cursor < content.length) {
    const skillMatch = findKnownSkillTag(content, cursor, skillNames);
    let nextMatch:
      | {
          index: number;
          text: string;
          kind: "file" | "skill";
        }
      | undefined = skillMatch
        ? {
            index: skillMatch.index,
            text: skillMatch.tag,
            kind: "skill",
          }
        : undefined;

    for (const path of uniquePaths) {
      const index = content.indexOf(path, cursor);
      if (index < 0) continue;
      if (
        !nextMatch ||
        index < nextMatch.index ||
        (index === nextMatch.index && path.length > nextMatch.text.length)
      ) {
        nextMatch = { index, text: path, kind: "file" };
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
      <span
        key={`special-tag-${partIndex}`}
        className={cn(
          "mx-0.5 inline-flex items-center rounded-full border px-2 py-px align-baseline font-mono text-xs",
          nextMatch.kind === "file"
            ? "border-primary/30 bg-primary/10 text-primary"
            : "border-usage-violet/30 bg-usage-violet/10 text-usage-violet",
        )}
        data-special-tag={nextMatch.kind}
      >
        {nextMatch.text}
      </span>,
    );
    partIndex += 1;
    cursor = nextMatch.index + nextMatch.text.length;
  }

  return nodes;
}

function isLongUserContent(content: string): boolean {
  return (
    content.length > USER_TEXT_COLLAPSE_CHARACTER_THRESHOLD
    || content.split(/\r\n|\r|\n/).length > USER_TEXT_COLLAPSE_LINE_THRESHOLD
  );
}

function UserMessageContent({
  content,
  filePaths,
  imageAttachments,
  skillNames,
  collapsible,
}: {
  content: string;
  filePaths: string[] | undefined;
  imageAttachments: ImageAttachment[] | undefined;
  skillNames: Set<string>;
  collapsible: boolean;
}): JSX.Element {
  const parsedReply = parseReplyMessage(content);
  content = parsedReply.text;
  const hasText = content.trim().length > 0;
  const canCollapse = collapsible && hasText && isLongUserContent(content);
  const [expanded, setExpanded] = useState(false);
  const textId = useId();
  const nodes = hasText ? renderUserTextNodes(content, filePaths, skillNames) : [];

  return (
    <>
      {imageAttachments && imageAttachments.length > 0 ? (
        <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {imageAttachments.map((attachment) => (
            <Tooltip key={attachment.upload_id}>
              <TooltipTrigger asChild>
                <a
                  className="flex min-w-0 flex-col gap-2 rounded-md border border-primary/30 bg-background p-2 text-inherit"
                  href={attachment.preview_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <img
                    className="block max-h-96 w-full rounded-sm bg-muted object-contain"
                    src={attachment.preview_url}
                    alt={attachment.name}
                  />
                  <span className="block max-w-full truncate text-xs text-muted-foreground">{attachment.name}</span>
                </a>
              </TooltipTrigger>
              <TooltipContent>{attachment.name}</TooltipContent>
            </Tooltip>
          ))}
        </div>
      ) : null}
      {parsedReply.snippets.length > 0 ? (
        <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {parsedReply.snippets.map((snippet, index) => (
            <ReplySnippetCard key={index} quote={snippet.quote} comment={snippet.comment} />
          ))}
        </div>
      ) : null}
      {hasText ? (
        <p
          id={canCollapse ? textId : undefined}
          className={cn(
            "m-0 wrap-anywhere whitespace-pre-wrap",
            canCollapse && !expanded && "max-h-48 overflow-hidden mask-b-from-60%",
          )}
          data-user-text
          data-collapsed={canCollapse && !expanded ? "true" : undefined}
        >
          {nodes}
        </p>
      ) : null}
      {canCollapse ? (
        <div className="mt-2 flex justify-end">
          <Button
            type="button"
            variant="ghost"
            size="xs"
            aria-controls={textId}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse user input" : "Show full user input"}
            onClick={() => setExpanded((current) => !current)}
          >
            {expanded ? "Collapse input" : "Show full input"}
          </Button>
        </div>
      ) : null}
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
  const skillNames = useSkillCatalog();
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
      <div className="mb-1 flex items-center gap-2 font-mono text-xs text-muted-foreground">
        <span
          className={cn(
            "size-1.5 shrink-0 rounded-full",
            subAgentStatus === "running" ? "animate-pulse bg-primary" : "bg-muted-foreground",
          )}
          data-subagent-status={subAgentStatus === "running" ? "running" : "done"}
        />
        <span>{subAgentName ?? "sub_agent"}</span>
      </div>
    ) : null;

  if (item.kind === "message") {
    if (item.role === "assistant" && item.content.trim() === "[compacted context]") {
      return (
        <div
          className="flex w-full animate-in flex-col items-center gap-1 fade-in"
          data-timeline-entry="compaction"
          data-timeline-item-id={item.itemId}
        >
          <Separator />
          <span className="text-xs text-muted-foreground" data-compaction-label>compacted context</span>
        </div>
      );
    }

    const roleClass: RoleClass =
      item.role === "user" ? "user"
      : item.role === "error" ? "error"
      : item.role === "notice" ? "notice"
      : item.role === "debug" ? "debug"
      : "assistant";

    const canCopyTurn = item.role === "user" || item.role === "assistant";
    const canFork =
      onForkMessage
      && item.messageId
      && !item.subAgentId
      && item.role === "assistant";
    const turnCopyAction = canCopyTurn ? (
      <CopyShortcut
        text={item.content}
        ariaLabel="Copy turn"
      />
    ) : null;
    const forkAction = canFork ? (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            aria-label="Fork conversation"
            onClick={() => onForkMessage(item.messageId!)}
          >
            <SplitIcon className="rotate-180" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Fork conversation</TooltipContent>
      </Tooltip>
    ) : null;
    const turnActions = turnCopyAction || forkAction ? (
      <div
        className={cn(
          "pointer-events-none mt-1 flex gap-1 opacity-0 transition-opacity group-focus-within/entry:pointer-events-auto group-focus-within/entry:opacity-100 group-hover/entry:pointer-events-auto group-hover/entry:opacity-100",
          roleClass === "user" ? "justify-end" : "justify-start",
        )}
        data-timeline-actions
      >
        {turnCopyAction}
        {forkAction}
      </div>
    ) : null;

    const entry = (
      <div
        className={cn("group/entry animate-in fade-in", ENTRY_ROLE_CLASSES[roleClass])}
        data-timeline-entry={roleClass}
        data-timeline-item-id={item.itemId}
      >
        {subAgentBanner}
        <div className={CONTENT_ROLE_CLASSES[roleClass]} data-timeline-content>
          {item.markdown && roleClass !== "user" ? (
            <MarkdownContent content={item.content} copyable={item.role === "assistant"} />
          ) : (
            <UserMessageContent
              content={item.content}
              filePaths={item.role === "user" ? item.filePaths : undefined}
              imageAttachments={item.role === "user" ? item.imageAttachments : undefined}
              skillNames={skillNames}
              collapsible={item.role === "user"}
            />
          )}
        </div>
        {turnActions}
      </div>
    );

    if (isCompactionSummaryMessage(item)) {
      return (
        <>
          {entry}
          <div className="flex w-full flex-col items-center" data-timeline-entry="compaction-summary-end">
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
          className="m-0 animate-in fade-in"
          data-timeline-entry="thinking"
          data-bare="true"
          data-timeline-item-id={item.itemId}
        >
          {subAgentBanner}
          <div className="mb-1 text-xs font-medium text-muted-foreground">{item.title}</div>
          <div className={THINKING_BODY_CLASSES}>
            <MarkdownContent content={item.content} />
          </div>
        </div>
      );
    }

    return (
      <div
        className="animate-in fade-in"
        data-timeline-entry="thinking"
        data-timeline-item-id={item.itemId}
      >
        {subAgentBanner}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-full justify-start"
          aria-expanded={!thinkingCollapsed}
          onClick={() => setThinkingCollapsedState({
            collapsed: !thinkingCollapsed,
            closeSignal,
          })}
        >
          <ChevronRightIcon
            data-icon="inline-start"
            className={cn("transition-transform", !thinkingCollapsed && "rotate-90")}
          />
          <span>{item.title}</span>
        </Button>
        {!thinkingCollapsed ? (
          <div className={cn("mt-1", THINKING_BODY_CLASSES)}>
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
        className="m-0 animate-in fade-in"
        data-timeline-entry="tool"
        data-bare="true"
        data-timeline-item-id={item.itemId}
      >
        {subAgentBanner}
        <div className="flex flex-col gap-2">
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
      className="animate-in fade-in"
      data-timeline-entry="tool"
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
            className="group/tool-trigger w-full justify-start"
          >
            <ChevronRightIcon
              data-icon="inline-start"
              className="transition-transform group-data-[state=open]/tool-trigger:rotate-90"
            />
            <span>{item.label}</span>
            {item.status === "running" ? (
              <Spinner className="ml-auto" aria-label="running" />
            ) : null}
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-1 flex flex-col gap-2">
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
