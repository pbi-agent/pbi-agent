import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteSession, fetchSessions, updateSession } from "../api";
import { forgetLastOpenedSessionId } from "../hooks/useLastOpenedSession";
import { useSidebarStore } from "../hooks/useSidebar";
import type { SessionDetailPayload, SessionRecord } from "../types";
import { DeleteSessionModal } from "./session/DeleteSessionModal";
import { SessionSidebar } from "./session/SessionSidebar";

/**
 * Global session-history context panel rendered inside the unified app
 * sidebar's context slot. It owns the sessions list query, rename/delete
 * mutations, and the delete confirmation dialog so the panel can render on
 * every primary route (sessions, board, dashboard) without duplicating state.
 *
 * Behaviour intentionally mirrors the previous in-page sidebar so this is a
 * purely structural refactor — no backend, contract, or behavioural changes.
 */
export function AppSessionsContextPanel() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>();
  const closeSidebar = useSidebarStore((state) => state.close);
  const [pendingDeleteSession, setPendingDeleteSession] = useState<SessionRecord | null>(null);

  const sessionsQuery = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
    refetchInterval: 12_000,
  });

  const deleteSessionMutation = useMutation({
    mutationFn: deleteSession,
  });

  const updateSessionMutation = useMutation({
    mutationFn: ({ sessionId, title }: { sessionId: string; title: string }) =>
      updateSession(sessionId, { title }),
    onSuccess: (updatedSession) => {
      client.setQueryData<SessionRecord[] | undefined>(["sessions"], (sessions) =>
        (sessions ?? []).map((session) =>
          session.session_id === updatedSession.session_id ? updatedSession : session,
        ),
      );
      client.setQueryData<SessionDetailPayload | undefined>(
        ["session", updatedSession.session_id],
        (detail) => (detail ? { ...detail, session: updatedSession } : detail),
      );
      void client.invalidateQueries({ queryKey: ["sessions"] });
      void client.invalidateQueries({ queryKey: ["bootstrap"] });
      void client.invalidateQueries({ queryKey: ["session", updatedSession.session_id] });
    },
  });

  const handleNewSession = () => {
    void navigate("/sessions");
    closeSidebar();
  };

  const handleResumeSession = (sessionId: string) => {
    void navigate(`/sessions/${encodeURIComponent(sessionId)}`);
  };

  const handleUpdateSessionTitle = async (session: SessionRecord, title: string) => {
    await updateSessionMutation.mutateAsync({
      sessionId: session.session_id,
      title,
    });
  };

  const handleDeleteSession = async () => {
    if (!pendingDeleteSession) return;
    const deletingActive = pendingDeleteSession.session_id === routeSessionId;
    await deleteSessionMutation.mutateAsync(pendingDeleteSession.session_id);
    forgetLastOpenedSessionId(pendingDeleteSession.session_id);
    client.setQueryData<SessionRecord[] | undefined>(["sessions"], (sessions) =>
      (sessions ?? []).filter(
        (session) => session.session_id !== pendingDeleteSession.session_id,
      ),
    );
    setPendingDeleteSession(null);
    await client.invalidateQueries({ queryKey: ["sessions"] });
    if (deletingActive) {
      void navigate("/sessions", { replace: true });
    }
  };

  const isDeleteBusy = deleteSessionMutation.isPending;

  return (
    <>
      <SessionSidebar
        sessions={sessionsQuery.data ?? []}
        isLoading={sessionsQuery.isLoading}
        activeSessionId={routeSessionId ?? null}
        onNewSession={handleNewSession}
        onResumeSession={handleResumeSession}
        onUpdateSession={handleUpdateSessionTitle}
        onDeleteSession={(session) => {
          deleteSessionMutation.reset();
          setPendingDeleteSession(session);
        }}
      />
      {pendingDeleteSession ? (
        <DeleteSessionModal
          session={pendingDeleteSession}
          isDeleting={isDeleteBusy}
          error={deleteSessionMutation.error?.message ?? null}
          onConfirm={() => {
            void handleDeleteSession();
          }}
          onClose={() => {
            if (!isDeleteBusy) {
              deleteSessionMutation.reset();
              setPendingDeleteSession(null);
            }
          }}
        />
      ) : null}
    </>
  );
}
