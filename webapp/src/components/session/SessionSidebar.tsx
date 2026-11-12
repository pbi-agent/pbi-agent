import { type FormEvent, type MouseEvent, useState } from "react";
import { Link } from "react-router-dom";
import {
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  Trash2Icon,
} from "lucide-react";
import type { SessionRecord } from "../../types";
import { MetaBadge } from "../MetaBadge";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Input } from "../ui/input";
import { Kbd } from "../ui/kbd";
import { Skeleton } from "../ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { TruncatedText } from "../TruncatedText";
import { EmptyState } from "../shared/EmptyState";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { SidebarSearchField } from "./SidebarSearchField";

const NEW_SESSION_SHORTCUT = "Ctrl+Shift+O";

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function sessionHref(sessionId: string): string {
  return `/sessions/${encodeURIComponent(sessionId)}`;
}

function shouldResumeInCurrentTab(event: MouseEvent<HTMLAnchorElement>): boolean {
  return (
    event.button === 0 &&
    !event.altKey &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey &&
    !event.defaultPrevented
  );
}

function isProcessingSession(status: SessionRecord["status"]): boolean {
  return status === "starting" || status === "running";
}

export type SessionSidebarProps = {
  sessions: SessionRecord[];
  isLoading: boolean;
  activeSessionId: string | null;
  onNewSession: () => void;
  onResumeSession: (sessionId: string) => void;
  onUpdateSession: (session: SessionRecord, title: string) => Promise<void>;
  onDeleteSession: (session: SessionRecord) => void;
  searchQuery?: string;
  onSearchQueryChange?: (query: string) => void;
};

/**
 * Session list panel rendered inside the unified app sidebar's context slot.
 * It owns inline edit/delete affordances for each saved session but no longer
 * renders primary navigation, settings, or its own collapse toggle — those
 * concerns belong to the shared {@link AppSidebarLayout}.
 */
export function SessionSidebar({
  sessions,
  isLoading,
  activeSessionId,
  onNewSession,
  onResumeSession,
  onUpdateSession,
  onDeleteSession,
  searchQuery = "",
  onSearchQueryChange,
}: SessionSidebarProps) {
  const [openMenuSessionId, setOpenMenuSessionId] = useState<string | null>(null);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [savingSessionId, setSavingSessionId] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

  const beginEdit = (session: SessionRecord) => {
    setOpenMenuSessionId(null);
    setEditingSessionId(session.session_id);
    setDraftTitle(session.title || "Untitled session");
    setEditError(null);
  };

  const cancelEdit = () => {
    if (savingSessionId) return;
    setEditingSessionId(null);
    setDraftTitle("");
    setEditError(null);
  };

  const saveEdit = async (event: FormEvent<HTMLFormElement>, session: SessionRecord) => {
    event.preventDefault();
    const nextTitle = draftTitle.trim();
    if (!nextTitle || nextTitle === session.title || savingSessionId) return;
    setSavingSessionId(session.session_id);
    setEditError(null);
    try {
      await onUpdateSession(session, nextTitle);
      setEditingSessionId(null);
      setDraftTitle("");
    } catch (error) {
      setEditError(error instanceof Error ? error.message : "Unable to update session title.");
    } finally {
      setSavingSessionId(null);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 px-3 pt-3" aria-label="Session list">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Sessions</h2>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onNewSession}
              aria-keyshortcuts={NEW_SESSION_SHORTCUT}
            >
              <PlusIcon data-icon="inline-start" />
              New
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <span>New session</span>
            <Kbd>{NEW_SESSION_SHORTCUT}</Kbd>
          </TooltipContent>
        </Tooltip>
      </div>

      <SidebarSearchField
        value={searchQuery}
        onChange={(nextQuery) => onSearchQueryChange?.(nextQuery)}
        placeholder="Search sessions"
        ariaLabel="Search sessions"
        clearLabel="Clear session search"
      />

      <div className="flex min-h-0 flex-1 flex-col gap-px overflow-y-auto pt-1 pb-3">
        {isLoading ? (
          <>
            <Skeleton className="h-13 w-full" />
            <Skeleton className="h-13 w-full" />
            <Skeleton className="h-13 w-full" />
          </>
        ) : sessions.length === 0 ? (
          <EmptyState
            title={searchQuery.trim() ? "No matching sessions" : "No sessions"}
            description={
              searchQuery.trim()
                ? "Try a different search term"
                : "Start a new session to begin"
            }
          />
        ) : (
          sessions.map((session) => {
            const menuOpen = openMenuSessionId === session.session_id;
            const isEditing = editingSessionId === session.session_id;
            const isSaving = savingSessionId === session.session_id;
            const trimmedDraft = draftTitle.trim();
            const saveDisabled = !trimmedDraft || trimmedDraft === session.title || isSaving;
            const isProcessing = isProcessingSession(session.status);
            return (
              <div
                key={session.session_id}
                data-active={activeSessionId === session.session_id || undefined}
                data-menu-open={menuOpen || undefined}
                data-editing={isEditing || undefined}
                className="group/session relative w-full rounded-md transition-colors hover:bg-muted data-active:bg-primary/10 data-active:hover:bg-primary/15"
              >
                {isEditing ? (
                  <form
                    className="flex flex-col gap-2 p-2"
                    onSubmit={(event) => {
                      void saveEdit(event, session);
                    }}
                  >
                    <label className="sr-only" htmlFor={`session-title-${session.session_id}`}>
                      Session title
                    </label>
                    <Input
                      id={`session-title-${session.session_id}`}
                      value={draftTitle}
                      onChange={(event) => setDraftTitle(event.target.value)}
                      autoFocus
                      aria-invalid={Boolean(editError)}
                    />
                    {editError ? (
                      <p role="alert" className="text-xs text-destructive">{editError}</p>
                    ) : null}
                    <div className="flex items-center gap-2">
                      <Button type="submit" size="sm" disabled={saveDisabled}>
                        {isSaving ? "Saving…" : "Save"}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={isSaving}
                        onClick={cancelEdit}
                      >
                        Cancel
                      </Button>
                    </div>
                  </form>
                ) : (
                  <>
                      <Link
                        className="flex min-h-13 w-full min-w-0 flex-col items-stretch justify-center gap-0.5 rounded-md px-3 py-2 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                        to={sessionHref(session.session_id)}
                        onClick={(event) => {
                          setOpenMenuSessionId(null);
                          if (!shouldResumeInCurrentTab(event)) {
                            return;
                          }
                          event.preventDefault();
                          onResumeSession(session.session_id);
                        }}
                      >
                        <TruncatedText
                          tooltipSide="right"
                          transitionKey={session.title ? session.session_id : undefined}
                          className="block w-full text-sm font-medium text-foreground group-hover/session:pr-7 group-data-active/session:text-primary group-data-menu-open/session:pr-7"
                        >
                          {session.title || "Untitled session"}
                        </TruncatedText>
                        <div className="flex min-w-0 items-center justify-start gap-2 text-xs text-muted-foreground">
                          <time className="inline-flex min-h-6 items-center whitespace-nowrap">{formatDate(session.updated_at)}</time>
                          {isProcessing ? (
                            <span
                              className="inline-flex shrink-0 items-center justify-center text-primary"
                              role="status"
                              aria-label="Session processing"
                            >
                              <LoadingSpinner size="sm" />
                            </span>
                          ) : null}
                          <MetaBadge>
                            {session.model}
                          </MetaBadge>
                        </div>
                      </Link>

                    <div className="pointer-events-none absolute top-2 right-2 opacity-0 transition-opacity group-hover/session:pointer-events-auto group-hover/session:opacity-100 group-data-menu-open/session:pointer-events-auto group-data-menu-open/session:opacity-100 has-focus-visible:pointer-events-auto has-focus-visible:opacity-100">
                    <DropdownMenu
                      open={menuOpen}
                      onOpenChange={(open) => {
                        setOpenMenuSessionId(open ? session.session_id : null);
                      }}
                    >
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-xs"
                          aria-label={`Open actions for ${session.title || "Untitled session"}`}
                          onClick={(event) => event.stopPropagation()}
                        >
                          <MoreHorizontalIcon />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuGroup>
                          <DropdownMenuItem
                            onClick={() => beginEdit(session)}
                          >
                            <PencilIcon />
                            Edit title
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            variant="destructive"
                            onClick={() => {
                              setOpenMenuSessionId(null);
                              onDeleteSession(session);
                            }}
                          >
                            <Trash2Icon />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuGroup>
                      </DropdownMenuContent>
                    </DropdownMenu>
                    </div>
                  </>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
