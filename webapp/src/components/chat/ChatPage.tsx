import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import {
  ApiError,
  createChatSession,
  deleteSession,
  expandChatInput,
  fetchSessionDetail,
  fetchSessions,
  requestNewChat,
  submitChatInput,
  uploadChatImages,
} from "../../api";
import type { HistoryItem, SessionRecord, TimelineItem } from "../../types";
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
  const navigate = useNavigate();
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inputWarnings, setInputWarnings] = useState<string[]>([]);
  const [pendingDeleteSession, setPendingDeleteSession] = useState<SessionRecord | null>(null);
  const composerRef = useRef<ComposerHandle>(null);
  const lastResolvedSessionIdRef = useRef<string | null>(null);
  const hydratedRouteKeyRef = useRef<string | null>(null);
  const liveRequestRouteKeyRef = useRef<string | null>(null);
  const [awaitingBlankChat, setAwaitingBlankChat] = useState(false);

  const {
    liveSessionId,
    resumeSessionId,
    connection,
    inputEnabled,
    sessionUsage,
    turnUsage,
    sessionEnded,
    fatalError,
    items,
    subAgents,
    waitMessage,
  } = useChatStore(
    useShallow((state) => ({
      liveSessionId: state.liveSessionId,
      resumeSessionId: state.resumeSessionId,
      connection: state.connection,
      inputEnabled: state.inputEnabled,
      sessionUsage: state.sessionUsage,
      turnUsage: state.turnUsage,
      sessionEnded: state.sessionEnded,
      fatalError: state.fatalError,
      items: state.items,
      subAgents: state.subAgents,
      waitMessage: state.waitMessage,
    })),
  );

  const setRouteState = useChatStore((state) => state.setRouteState);
  const attachLiveSession = useChatStore((state) => state.attachLiveSession);

  const sessionsQuery = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
    refetchInterval: 12_000,
  });

  const sessionDetailQuery = useQuery({
    queryKey: ["session", routeSessionId],
    queryFn: () => fetchSessionDetail(routeSessionId!),
    enabled: Boolean(routeSessionId),
    retry: false,
  });

  const createSessionMutation = useMutation({
    mutationFn: createChatSession,
    onSuccess: (session, variables) =>
      attachLiveSession(
        session.live_session_id,
        session.resume_session_id,
        Boolean(variables.resume_session_id),
      ),
  });
  const createSession = createSessionMutation.mutate;
  const createSessionAsync = createSessionMutation.mutateAsync;

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

  const requestNewChatMutation = useMutation({
    mutationFn: ({
      liveSessionId,
      profileId = null,
    }: {
      liveSessionId: string;
      profileId?: string | null;
    }) => requestNewChat(liveSessionId, profileId),
  });

  useLiveChatEvents(liveSessionId);

  useEffect(() => {
    if (awaitingBlankChat && resumeSessionId === null) {
      setAwaitingBlankChat(false);
    }
  }, [awaitingBlankChat, resumeSessionId]);

  useEffect(() => {
    // While a new-blank-chat transition is in flight, hold off — prevents the
    // stale-route render (zustand update before react-router propagates) from
    // creating a spurious resume session.
    if (awaitingBlankChat) return;

    const routeKey = routeSessionId ?? "__new__";

    if (routeSessionId) {
      if (liveSessionId && resumeSessionId === routeSessionId) {
        hydratedRouteKeyRef.current = routeKey;
        liveRequestRouteKeyRef.current = routeKey;
        return;
      }

      if (!sessionDetailQuery.isSuccess) {
        if (sessionDetailQuery.isError && hydratedRouteKeyRef.current !== routeKey) {
          setRouteState(routeSessionId, []);
          hydratedRouteKeyRef.current = routeKey;
          liveRequestRouteKeyRef.current = null;
        }
        return;
      }

      if (hydratedRouteKeyRef.current !== routeKey) {
        // Always preload persisted history. If an active live session also replays those
        // same messages via the WebSocket snapshot, matching item IDs let the store
        // upsert them instead of duplicating them.
        const historyItems = sessionDetailQuery.data.history_items.map(mapHistoryItem);
        setRouteState(routeSessionId, historyItems);
        hydratedRouteKeyRef.current = routeKey;
        liveRequestRouteKeyRef.current = null;
      }

      if (liveRequestRouteKeyRef.current !== routeKey) {
        createSession({ resume_session_id: routeSessionId });
        liveRequestRouteKeyRef.current = routeKey;
      }
      return;
    }

    if (hydratedRouteKeyRef.current !== routeKey) {
      // Don't wipe the store if we already have an active live session waiting for a
      // new-chat response — the WebSocket is still open and will deliver session_state.
      if (liveSessionId && resumeSessionId === null && !sessionEnded) {
        hydratedRouteKeyRef.current = routeKey;
        liveRequestRouteKeyRef.current = routeKey;
        return;
      }
      setRouteState(null, []);
      hydratedRouteKeyRef.current = routeKey;
      liveRequestRouteKeyRef.current = null;
    }

    if (liveSessionId && resumeSessionId === null && !sessionEnded) {
      liveRequestRouteKeyRef.current = routeKey;
      return;
    }

    if (liveRequestRouteKeyRef.current !== routeKey) {
      createSession({});
      liveRequestRouteKeyRef.current = routeKey;
    }
  }, [
    awaitingBlankChat,
    createSession,
    liveSessionId,
    resumeSessionId,
    routeSessionId,
    sessionDetailQuery.data,
    sessionDetailQuery.isError,
    sessionDetailQuery.isSuccess,
    sessionEnded,
    setRouteState,
  ]);

  useEffect(() => {
    if (awaitingBlankChat) {
      return;
    }
    if (resumeSessionId && !routeSessionId) {
      navigate(`/chat/${encodeURIComponent(resumeSessionId)}`, { replace: true });
    }
  }, [awaitingBlankChat, navigate, resumeSessionId, routeSessionId]);

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
      client.invalidateQueries({ queryKey: ["session", resumeSessionId] });
    }
    lastResolvedSessionIdRef.current = resumeSessionId;
  }, [client, resumeSessionId]);

  const activeSessionRecord = routeSessionId
    ? sessionDetailQuery.data?.session ??
      (sessionsQuery.data?.find((session) => session.session_id === routeSessionId) ?? {
        session_id: routeSessionId,
        directory: workspaceRoot ?? "",
        provider: "",
        provider_id: null,
        model: "",
        profile_id: null,
        previous_id: null,
        title: "",
        total_tokens: 0,
        input_tokens: 0,
        output_tokens: 0,
        cost_usd: 0,
        created_at: "",
        updated_at: "",
      })
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

  const openBlankChat = async ({
    replace = false,
    awaitCreate = false,
  }: {
    replace?: boolean;
    awaitCreate?: boolean;
  } = {}) => {
    const routeKey = "__new__";
    setAwaitingBlankChat(false);
    liveRequestRouteKeyRef.current = routeKey;
    navigate("/chat", { replace });
    setRouteState(null, []);
    hydratedRouteKeyRef.current = routeKey;
    if (awaitCreate) {
      await createSessionAsync({});
      return;
    }
    createSession({});
  };

  const transitionToBlankChat = async ({
    replace = false,
    awaitCreate = false,
  }: {
    replace?: boolean;
    awaitCreate?: boolean;
  } = {}) => {
    const currentLiveSessionId = liveSessionId;
    setAwaitingBlankChat(true);

    if (currentLiveSessionId && !sessionEnded) {
      try {
        await requestNewChatMutation.mutateAsync({ liveSessionId: currentLiveSessionId });
        attachLiveSession(currentLiveSessionId, null, false);
        navigate("/chat", { replace });
      } catch {
        await openBlankChat({ replace, awaitCreate });
      }
    } else {
      await openBlankChat({ replace, awaitCreate });
    }

    window.setTimeout(() => composerRef.current?.focus(), 100);
  };

  const handleNewSession = async () => {
    setSidebarOpen(false);
    await transitionToBlankChat();
  };

  const handleDeleteSession = async () => {
    if (!pendingDeleteSession) return;
    const deletingActive = pendingDeleteSession.session_id === routeSessionId;

    await deleteSessionMutation.mutateAsync(pendingDeleteSession.session_id);
    client.setQueryData<SessionRecord[] | undefined>(["sessions"], (sessions) =>
      (sessions ?? []).filter(
        (session) => session.session_id !== pendingDeleteSession.session_id,
      ),
    );
    setPendingDeleteSession(null);
    await client.invalidateQueries({ queryKey: ["sessions"] });

    if (deletingActive) {
      await transitionToBlankChat({ replace: true, awaitCreate: true });
    }
  };

  const canDeleteActiveSession = Boolean(routeSessionId && activeSessionRecord);
  const isDeleteBusy =
    deleteSessionMutation.isPending
    || createSessionMutation.isPending
    || requestNewChatMutation.isPending;
  const sessionDetailError = routeSessionId ? sessionDetailQuery.error : null;
  const sessionNotFound =
    routeSessionId
    && sessionDetailError instanceof ApiError
    && sessionDetailError.status === 404;
  const sessionDetailLoadError =
    routeSessionId && sessionDetailQuery.isError && !sessionNotFound
      ? "Unable to load this chat right now."
      : null;

  return (
    <section className={`chat-layout ${sidebarOpen ? "chat-layout--sidebar-open" : ""}`}>
      <div className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}>
        <SessionSidebar
          sessions={sessionsQuery.data ?? []}
          isLoading={sessionsQuery.isLoading}
          activeSessionId={routeSessionId ?? resumeSessionId}
          workspaceRoot={workspaceRoot}
          onNewSession={() => { void handleNewSession(); }}
          onResumeSession={(sessionId) => {
            navigate(`/chat/${encodeURIComponent(sessionId)}`);
            setSidebarOpen(false);
          }}
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
        {createSessionMutation.error ? (
          <div className="banner banner--error">{createSessionMutation.error.message}</div>
        ) : null}
        {sessionDetailLoadError ? (
          <div className="banner banner--error">{sessionDetailLoadError}</div>
        ) : null}

        {sessionNotFound ? (
          <div className="empty-state">
            <div className="empty-state__title">Session not found</div>
            <div className="empty-state__description">
              {sessionDetailError?.message ?? "This chat does not exist in the current workspace."}
            </div>
            <button
              type="button"
              className="btn btn--primary empty-state__action"
              onClick={() => { void handleNewSession(); }}
            >
              Start new chat
            </button>
          </div>
        ) : (
          <>
            <ChatTimeline
              items={items}
              subAgents={subAgents}
              connection={connection}
              waitMessage={waitMessage}
            />

            <Composer
              ref={composerRef}
              inputEnabled={inputEnabled}
              sessionEnded={sessionEnded}
              liveSessionId={liveSessionId}
              supportsImageInputs={supportsImageInputs}
              isSubmitting={sendInputMutation.isPending}
              onSubmit={handleSubmit}
            />
          </>
        )}
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

function mapHistoryItem(item: HistoryItem): TimelineItem {
  return {
    kind: "message",
    itemId: item.item_id,
    role: item.role,
    content: item.content,
    filePaths: item.file_paths,
    imageAttachments: item.image_attachments,
    markdown: item.markdown,
  };
}
