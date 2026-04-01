import { useEffect, useRef, useState } from "react";
import type { SessionRecord } from "../../types";
import { EmptyState } from "../shared/EmptyState";

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </svg>
  );
}

function MoreIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <circle cx="5" cy="12" r="2" />
      <circle cx="12" cy="12" r="2" />
      <circle cx="19" cy="12" r="2" />
    </svg>
  );
}

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
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (
        containerRef.current &&
        event.target instanceof Node &&
        !containerRef.current.contains(event.target)
      ) {
        setOpenMenuSessionId(null);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenMenuSessionId(null);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  if (!isOpen) {
    return (
      <div className="sidebar__collapsed">
        <button
          type="button"
          className="sidebar__toggle"
          onClick={onToggle}
          title="Show sessions"
        >
          &#9654;
        </button>
        <button
          type="button"
          className="btn btn--primary btn--icon"
          onClick={onNewSession}
          title="New session"
        >
          +
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="sidebar__header">
        <span className="sidebar__title">Chat History</span>
        <div className="sidebar__header-actions">
          <button type="button" className="btn btn--primary btn--sm" onClick={onNewSession}>
            + New
          </button>
          <button
            type="button"
            className="sidebar__toggle"
            onClick={onToggle}
            title="Hide sessions"
          >
            &#9664;
          </button>
        </div>
      </div>

      {workspaceRoot ? (
        <div className="sidebar__workspace">
          <span className="sidebar__workspace-path" title={workspaceRoot}>
            {workspaceRoot}
          </span>
        </div>
      ) : null}

      <div className="sidebar__list" ref={containerRef}>
        {isLoading ? (
          <>
            <div className="skeleton skeleton--card" />
            <div className="skeleton skeleton--card" />
            <div className="skeleton skeleton--card" />
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
                <button
                  type="button"
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
                    <span className="session-card__model">{session.model}</span>
                  </div>
                </button>

                <button
                  type="button"
                  className="session-card__menu-trigger"
                  aria-label={`Open actions for ${session.title || "Untitled session"}`}
                  aria-expanded={menuOpen}
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpenMenuSessionId((current) =>
                      current === session.session_id ? null : session.session_id,
                    );
                  }}
                >
                  <MoreIcon />
                </button>

                {menuOpen ? (
                  <div className="session-card__menu" role="menu">
                    <button
                      type="button"
                      className="session-card__menu-item session-card__menu-item--danger"
                      role="menuitem"
                      onClick={() => {
                        setOpenMenuSessionId(null);
                        onDeleteSession(session);
                      }}
                    >
                      <TrashIcon />
                      Delete chat
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
