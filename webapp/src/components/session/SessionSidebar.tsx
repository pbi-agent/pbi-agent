import { type FormEvent, useState } from "react";
import {
  MoreHorizontalIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  PencilIcon,
  PlusIcon,
  SettingsIcon,
  Trash2Icon,
} from "lucide-react";
import type { SessionRecord } from "../../types";
import { useSettingsDialog } from "../../hooks/useSettingsDialog";
import { Badge } from "../ui/badge";
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

export function SessionSidebar({
  sessions,
  isLoading,
  activeSessionId,
  onNewSession,
  onResumeSession,
  onUpdateSession,
  onDeleteSession,
  onToggle,
  isOpen,
}: {
  sessions: SessionRecord[];
  isLoading: boolean;
  activeSessionId: string | null;
  onNewSession: () => void;
  onResumeSession: (sessionId: string) => void;
  onUpdateSession: (session: SessionRecord, title: string) => Promise<void>;
  onDeleteSession: (session: SessionRecord) => void;
  onToggle: () => void;
  isOpen: boolean;
}) {
  const [openMenuSessionId, setOpenMenuSessionId] = useState<string | null>(null);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [savingSessionId, setSavingSessionId] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const { openSettings } = useSettingsDialog();

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

  if (!isOpen) {
    return (
      <div className="sidebar__collapsed">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="sidebar__toggle"
          onClick={onToggle}
          title="Show sessions"
          aria-label="Show sessions"
        >
          <PanelLeftOpenIcon />
        </Button>
        <Button
          type="button"
          size="icon-sm"
          onClick={onNewSession}
          title="New session"
          aria-label="New session"
        >
          <PlusIcon />
        </Button>
        <button
          type="button"
          className="sidebar__collapsed-settings"
          title="Settings"
          aria-label="Settings"
          onClick={openSettings}
        >
          <SettingsIcon />
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="sidebar__header">
        <div className="sidebar__header-actions">
          <Button
            type="button"
            size="sm"
            className="sidebar__new-button"
            onClick={onNewSession}
          >
            <PlusIcon data-icon="inline-start" />
            New Session
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="sidebar__toggle"
            onClick={onToggle}
            title="Hide sessions"
            aria-label="Hide sessions"
          >
            <PanelLeftCloseIcon />
          </Button>
        </div>
      </div>

      <div className="sidebar__list">
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
                        <Badge variant="secondary" className="session-card__model">
                          {session.model}
                        </Badge>
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
                      <DropdownMenuContent align="end" className="session-card__menu">
                        <DropdownMenuGroup>
                          <DropdownMenuItem
                            className="session-card__menu-item"
                            onClick={() => beginEdit(session)}
                          >
                            <PencilIcon />
                            Edit title
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

      <div className="sidebar__footer">
        <button type="button" className="sidebar__footer-link" onClick={openSettings}>
          <SettingsIcon />
          <span>Settings</span>
        </button>
      </div>
    </>
  );
}
