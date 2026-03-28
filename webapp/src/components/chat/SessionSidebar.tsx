import type { SessionRecord } from "../../types";
import { EmptyState } from "../shared/EmptyState";

export function SessionSidebar({
  sessions,
  isLoading,
  activeSessionId,
  workspaceRoot,
  onNewSession,
  onResumeSession,
  onToggle,
  isOpen,
}: {
  sessions: SessionRecord[];
  isLoading: boolean;
  activeSessionId: string | null;
  workspaceRoot: string | undefined;
  onNewSession: () => void;
  onResumeSession: (sessionId: string) => void;
  onToggle: () => void;
  isOpen: boolean;
}) {
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
        <span className="sidebar__title">Sessions</span>
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

      <div className="sidebar__list">
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
          sessions.map((session) => (
            <button
              key={session.session_id}
              type="button"
              className={`session-card ${activeSessionId === session.session_id ? "session-card--active" : ""}`}
              onClick={() => onResumeSession(session.session_id)}
            >
              <span className="session-card__title">
                {session.title || "Untitled session"}
              </span>
              <div className="session-card__meta">
                <span>{session.updated_at.replace("T", " ").slice(0, 16)}</span>
                <span className="session-card__model">{session.model}</span>
              </div>
            </button>
          ))
        )}
      </div>
    </>
  );
}
