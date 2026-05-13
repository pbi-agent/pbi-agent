import { type FormEvent, useState } from "react";
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
import { Skeleton } from "../ui/skeleton";
import { EmptyState } from "../shared/EmptyState";

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

export type SessionSidebarProps = {
  sessions: SessionRecord[];
  isLoading: boolean;
  activeSessionId: string | null;
  onNewSession: () => void;
  onResumeSession: (sessionId: string) => void;
  onUpdateSession: (session: SessionRecord, title: string) => Promise<void>;
  onDeleteSession: (session: SessionRecord) => void;
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
    <div className="session-sidebar" aria-label="Session list">
      <div className="session-sidebar__header">
        <h2 className="session-sidebar__title">Sessions</h2>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="session-sidebar__new-button"
          onClick={onNewSession}
        >
          <PlusIcon data-icon="inline-start" />
          New
        </Button>
      </div>

      <div className="session-sidebar__list">
        {isLoading ? (
          <>
            <Skeleton className="skeleton skeleton--card" />
            <Skeleton className="skeleton skeleton--card" />
            <Skeleton className="skeleton skeleton--card" />
          </>
        ) : sessions.length === 0 ? (
          <EmptyState
            title="No sessions"
            description="Start a new session to begin"
          />
        ) : (
          sessions.map((session) => {
            const menuOpen = openMenuSessionId === session.session_id;
            const isEditing = editingSessionId === session.session_id;
            const isSaving = savingSessionId === session.session_id;
            const trimmedDraft = draftTitle.trim();
            const saveDisabled = !trimmedDraft || trimmedDraft === session.title || isSaving;
            return (
              <div
                key={session.session_id}
                className={`session-card ${activeSessionId === session.session_id ? "session-card--active" : ""}${menuOpen ? " session-card--menu-open" : ""}${isEditing ? " session-card--editing" : ""}`}
              >
                {isEditing ? (
                  <form
                    className="session-card__edit-form"
                    onSubmit={(event) => {
                      void saveEdit(event, session);
                    }}
                  >
                    <label className="session-card__edit-label" htmlFor={`session-title-${session.session_id}`}>
                      Session title
                    </label>
                    <Input
                      id={`session-title-${session.session_id}`}
                      className="session-card__edit-input"
                      value={draftTitle}
                      onChange={(event) => setDraftTitle(event.target.value)}
                      autoFocus
                      aria-invalid={Boolean(editError)}
                    />
                    {editError ? (
                      <p className="session-card__edit-error">{editError}</p>
                    ) : null}
                    <div className="session-card__edit-actions">
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
                    <Button
                      type="button"
                      variant="ghost"
                      className="session-card__main"
                      onClick={() => {
                        setOpenMenuSessionId(null);
                        onResumeSession(session.session_id);
                      }}
                    >
                      <span className="session-card__title">
                        {session.title || "Untitled session"}
                      </span>
                      <div className="session-card__meta">
                        <time className="session-card__time">{formatDate(session.updated_at)}</time>
                        <MetaBadge className="session-card__model">
                          {session.model}
                        </MetaBadge>
                      </div>
                    </Button>

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
                          size="icon-sm"
                          className="session-card__menu-trigger"
                          aria-label={`Open actions for ${session.title || "Untitled session"}`}
                          onClick={(event) => event.stopPropagation()}
                        >
                          <MoreHorizontalIcon />
                        </Button>
                      </DropdownMenuTrigger>
<DropdownMenuContent align="end">
                        <DropdownMenuGroup>
                          <DropdownMenuItem
                            className="session-card__menu-item"
                            onClick={() => beginEdit(session)}
                          >
                            <PencilIcon />
                            Edit
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            variant="destructive"
                            className="session-card__menu-item"
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
