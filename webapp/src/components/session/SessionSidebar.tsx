import { useState } from "react";
import {
  FolderGit2Icon,
  MoreHorizontalIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  PlusIcon,
  Trash2Icon,
} from "lucide-react";
import type { SessionRecord } from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
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
  workspaceRoot,
  onNewSession,
  onResumeSession,
  onDeleteSession,
  onToggle,
  isOpen,
}: {
  sessions: SessionRecord[];
  isLoading: boolean;
  activeSessionId: string | null;
  workspaceRoot: string | undefined;
  onNewSession: () => void;
  onResumeSession: (sessionId: string) => void;
  onDeleteSession: (session: SessionRecord) => void;
  onToggle: () => void;
  isOpen: boolean;
}) {
  const [openMenuSessionId, setOpenMenuSessionId] = useState<string | null>(null);

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
      </div>
    );
  }

  return (
    <>
      <div className="sidebar__header">
        <span className="sidebar__title">Session History</span>
        <div className="sidebar__header-actions">
          <Button type="button" size="sm" onClick={onNewSession}>
            <PlusIcon data-icon="inline-start" />
            New
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

      {workspaceRoot ? (
        <div className="sidebar__workspace">
          <Badge variant="outline" className="sidebar__workspace-path" title={workspaceRoot}>
            <FolderGit2Icon data-icon="inline-start" />
            {workspaceRoot}
          </Badge>
        </div>
      ) : null}

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
            return (
              <div
                key={session.session_id}
                className={`session-card ${activeSessionId === session.session_id ? "session-card--active" : ""}${menuOpen ? " session-card--menu-open" : ""}`}
              >
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
                    <Badge variant="secondary" className="session-card__model">{session.model}</Badge>
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
                        variant="destructive"
                        className="session-card__menu-item"
                        onClick={() => {
                          setOpenMenuSessionId(null);
                          onDeleteSession(session);
                        }}
                      >
                        <Trash2Icon />
                        Delete session
                      </DropdownMenuItem>
                    </DropdownMenuGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
