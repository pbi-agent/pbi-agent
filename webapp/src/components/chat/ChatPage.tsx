import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import {
  createChatSession,
  deleteSession,
  expandChatInput,
  fetchSessions,
  submitChatInput,
  uploadChatImages,
} from "../../api";
import type { SessionRecord } from "../../types";
import { useChatStore } from "../../store";
import { useLiveChatEvents } from "../../hooks/useLiveChatEvents";
import { ConnectionBadge } from "./ConnectionBadge";
import { DeleteSessionModal } from "./DeleteSessionModal";
import { SessionSidebar } from "./SessionSidebar";
import { ChatTimeline } from "./ChatTimeline";
import { UsageBar } from "./UsageBar";
import { Composer, type ComposerHandle } from "./Composer";

export function ChatPage({
  workspaceRoot,
  supportsImageInputs,
}: {
  workspaceRoot: string | undefined;
  supportsImageInputs: boolean;
}) {
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inputWarnings, setInputWarnings] = useState<string[]>([]);
  const [pendingDeleteSession, setPendingDeleteSession] = useState<SessionRecord | null>(null);
  const composerRef = useRef<ComposerHandle>(null);
  const lastResolvedSessionIdRef = useRef<string | null>(null);

  const {
    liveSessionId,
    resumeSessionId,
    connection,
    inputEnabled,
    waitMessage,
    sessionUsage,
    turnUsage,
    sessionEnded,
    fatalError,
    items,
    subAgents,
  } = useChatStore(
    useShallow((state) => ({
      liveSessionId: state.liveSessionId,
      resumeSessionId: state.resumeSessionId,
      connection: state.connection,
      inputEnabled: state.inputEnabled,
      waitMessage: state.waitMessage,
      sessionUsage: state.sessionUsage,
      turnUsage: state.turnUsage,
      sessionEnded: state.sessionEnded,
      fatalError: state.fatalError,
      items: state.items,
      subAgents: state.subAgents,
    })),
  );

  const switchLiveSession = useChatStore((state) => state.switchLiveSession);

  const sessionsQuery = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
    refetchInterval: 12_000,
  });

  const createSessionMutation = useMutation({
    mutationFn: createChatSession,
    onSuccess: (session) =>
      switchLiveSession(session.live_session_id, session.resume_session_id),
  });

  const sendInputMutation = useMutation({
    mutationFn: (payload: {
      text: string;
      file_paths: string[];
      image_paths: string[];
      image_upload_ids: string[];
    }) => {
      if (!liveSessionId) throw new Error("No live session available.");
      return submitChatInput(liveSessionId, payload);
    },
  });

  const deleteSessionMutation = useMutation({
    mutationFn: deleteSession,
  });

  const startedRef = useRef(false);
  const mutateRef = useRef(createSessionMutation.mutate);
  mutateRef.current = createSessionMutation.mutate;

  useLiveChatEvents(createSessionMutation.isSuccess ? liveSessionId : null);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    const resumeId = searchParams.get("session");
    if (resumeId) {
      mutateRef.current({ resume_session_id: resumeId });
      setSearchParams({}, { replace: true });
    } else {
      mutateRef.current(liveSessionId ? { live_session_id: liveSessionId } : {});
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (inputEnabled && liveSessionId && !sessionEnded) {
      composerRef.current?.focus();
    }
  }, [inputEnabled, liveSessionId, sessionEnded]);

  useEffect(() => {
    if (inputWarnings.length === 0) return undefined;
    const timeoutId = window.setTimeout(() => setInputWarnings([]), 5000);
    return () => window.clearTimeout(timeoutId);
  }, [inputWarnings]);

  useEffect(() => {
    const previous = lastResolvedSessionIdRef.current;
    if (resumeSessionId && resumeSessionId !== previous) {
      client.invalidateQueries({ queryKey: ["sessions"] });
    }
    lastResolvedSessionIdRef.current = resumeSessionId;
  }, [client, resumeSessionId]);

  const activeSessionRecord =
    resumeSessionId && sessionsQuery.data
      ? sessionsQuery.data.find((session) => session.session_id === resumeSessionId) ?? {
          session_id: resumeSessionId,
          directory: workspaceRoot ?? "",
          provider: "",
          model: "",
          previous_id: null,
          title: "",
          total_tokens: 0,
          input_tokens: 0,
          output_tokens: 0,
          cost_usd: 0,
          created_at: "",
          updated_at: "",
        }
      : null;

  const handleSubmit = async (payload: { text: string; images: File[] }) => {
    const { text, images } = payload;
    setInputWarnings([]);
    if (text.startsWith("/")) {
      await sendInputMutation.mutateAsync({
        text,
        file_paths: [],
        image_paths: [],
        image_upload_ids: [],
      });
      return;
    }

    const expanded = await expandChatInput(text);
    if (expanded.warnings.length > 0) {
      setInputWarnings(expanded.warnings);
    }

    const mergedImagePaths = Array.from(
      new Set(expanded.image_paths),
    );
    const uploadedImageIds =
      images.length > 0 && liveSessionId
        ? (await uploadChatImages(liveSessionId, images)).map(
            (image) => image.upload_id,
          )
        : [];
    await sendInputMutation.mutateAsync({
      text: expanded.text,
      file_paths: expanded.file_paths,
      image_paths: mergedImagePaths,
      image_upload_ids: uploadedImageIds,
    });
  };

  const handleDeleteSession = async () => {
    if (!pendingDeleteSession) return;
    const deletingActive = pendingDeleteSession.session_id === resumeSessionId;

    await deleteSessionMutation.mutateAsync(pendingDeleteSession.session_id);
    client.setQueryData<SessionRecord[] | undefined>(["sessions"], (sessions) =>
      (sessions ?? []).filter(
        (session) => session.session_id !== pendingDeleteSession.session_id,
      ),
    );
    setPendingDeleteSession(null);
    await client.invalidateQueries({ queryKey: ["sessions"] });

    if (deletingActive) {
      await createSessionMutation.mutateAsync({});
      window.setTimeout(() => composerRef.current?.focus(), 100);
    }
  };

  const canDeleteActiveSession = Boolean(resumeSessionId) && items.length > 0;
  const isDeleteBusy =
    deleteSessionMutation.isPending || createSessionMutation.isPending;

  return (
    <section className={`chat-layout ${sidebarOpen ? "chat-layout--sidebar-open" : ""}`}>
      <div className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}>
        <SessionSidebar
          sessions={sessionsQuery.data ?? []}
          isLoading={sessionsQuery.isLoading}
          activeSessionId={resumeSessionId}
          workspaceRoot={workspaceRoot}
          onNewSession={() => {
            createSessionMutation.mutate({});
            setSidebarOpen(false);
            setTimeout(() => composerRef.current?.focus(), 100);
          }}
          onResumeSession={(sessionId) =>
            createSessionMutation.mutate({ resume_session_id: sessionId })
          }
          onDeleteSession={(session) => {
            deleteSessionMutation.reset();
            setPendingDeleteSession(session);
          }}
          onToggle={() => setSidebarOpen((prev) => !prev)}
          isOpen={sidebarOpen}
        />
      </div>

      <div className="chat-panel">
        <div className="chat-topbar">
          <ConnectionBadge connection={connection} />
          <div className="chat-topbar__actions">
            <UsageBar sessionUsage={sessionUsage} turnUsage={turnUsage} />
            {canDeleteActiveSession ? (
              <button
                type="button"
                className="btn btn--ghost btn--icon btn--danger"
                title="Delete chat"
                onClick={() => {
                  if (!activeSessionRecord) return;
                  deleteSessionMutation.reset();
                  setPendingDeleteSession(activeSessionRecord);
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  <line x1="10" y1="11" x2="10" y2="17" />
                  <line x1="14" y1="11" x2="14" y2="17" />
                </svg>
              </button>
            ) : null}
          </div>
        </div>

        {inputWarnings.length > 0 ? (
          <div className="banner banner--notice">{inputWarnings.join(" ")}</div>
        ) : null}
        {fatalError ? <div className="banner banner--error">{fatalError}</div> : null}

        <ChatTimeline
          items={items}
          subAgents={subAgents}
          connection={connection}
        />

        <Composer
          ref={composerRef}
          inputEnabled={inputEnabled}
          sessionEnded={sessionEnded}
          liveSessionId={liveSessionId}
          supportsImageInputs={supportsImageInputs}
          waitMessage={waitMessage}
          isSubmitting={sendInputMutation.isPending}
          onSubmit={handleSubmit}
        />
      </div>

      {pendingDeleteSession ? (
        <DeleteSessionModal
          session={pendingDeleteSession}
          isDeleting={isDeleteBusy}
          error={deleteSessionMutation.error?.message ?? null}
          onConfirm={handleDeleteSession}
          onClose={() => {
            if (isDeleteBusy) return;
            deleteSessionMutation.reset();
            setPendingDeleteSession(null);
          }}
        />
      ) : null}
    </section>
  );
}
