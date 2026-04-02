import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import {
  ApiError,
  createChatSession,
  deleteSession,
  expandChatInput,
  fetchConfigBootstrap,
  fetchSessionDetail,
  fetchSessions,
  requestNewChat,
  setActiveModelProfile,
  setChatSessionProfile,
  submitChatInput,
  uploadChatImages,
} from "../../api";
import type { HistoryItem, ModelProfileView, SessionRecord, TimelineItem } from "../../types";
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
  const [pendingProfileId, setPendingProfileId] = useState<string | null>(null);

  const {
    liveSessionId,
    resumeSessionId,
    runtime,
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
      runtime: state.runtime,
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
  const updateRuntimeFromSession = useChatStore((state) => state.updateRuntimeFromSession);

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

  const configQuery = useQuery({
    queryKey: ["config-bootstrap"],
    queryFn: fetchConfigBootstrap,
    staleTime: 30_000,
  });

  const createSessionMutation = useMutation({
    mutationFn: createChatSession,
    onSuccess: (session, variables) =>
      attachLiveSession(session, Boolean(variables.resume_session_id)),
  });
  const createSession = createSessionMutation.mutate;
  const createSessionAsync = createSessionMutation.mutateAsync;

  const sendInputMutation = useMutation({
    mutationFn: (payload: {
      text: string;
      file_paths: string[];
      image_paths: string[];
      image_upload_ids: string[];
      profile_id?: string | null;
    }) => {
      if (!liveSessionId) throw new Error("No live session available.");
      return submitChatInput(liveSessionId, payload);
    },
    onSuccess: (session) => updateRuntimeFromSession(session),
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

  const setChatProfileMutation = useMutation({
    mutationFn: ({
      liveSessionId,
      profileId,
    }: {
      liveSessionId: string;
      profileId: string | null;
    }) => setChatSessionProfile(liveSessionId, profileId),
    onSuccess: (session) => {
      updateRuntimeFromSession(session);
      client.invalidateQueries({ queryKey: ["sessions"] });
      if (resumeSessionId) {
        client.invalidateQueries({ queryKey: ["session", resumeSessionId] });
      }
    },
  });

  const setActiveProfileMutation = useMutation({
    mutationFn: ({
      profileId,
      configRevision,
    }: {
      profileId: string | null;
      configRevision: string;
    }) => setActiveModelProfile(profileId, configRevision),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["config-bootstrap"] }),
        client.invalidateQueries({ queryKey: ["bootstrap"] }),
      ]);
    },
  });

  // Don't open a WebSocket until the routing effect has run at least once for this
  // mount (hydratedRouteKeyRef goes from null → routeKey). Without this guard the hook
  // would open a socket for any stale liveSessionId still in the Zustand store, then
  // immediately close it (CONNECTING → close) when the routing effect resets state,
  // producing a browser "WebSocket closed before connection established" warning.
  const effectiveLiveSessionId = hydratedRouteKeyRef.current !== null ? liveSessionId : null;
  useLiveChatEvents(effectiveLiveSessionId);

  useEffect(() => {
    if (awaitingBlankChat && resumeSessionId === null) {
      setAwaitingBlankChat(false);
    }
  }, [awaitingBlankChat, resumeSessionId]);

  useEffect(() => {
    if (pendingProfileId && runtime?.profile_id === pendingProfileId) {
      setPendingProfileId(null);
    }
  }, [pendingProfileId, runtime?.profile_id]);

  useEffect(() => {
    setPendingProfileId(null);
  }, [routeSessionId]);

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
      // Only applies on re-renders within the same mount (hydratedRouteKeyRef already set),
      // not on fresh mounts (null) where we always want to reset so a new default profile
      // is picked up correctly.
      const isFreshMount = hydratedRouteKeyRef.current === null;
      if (!isFreshMount && liveSessionId && resumeSessionId === null && !sessionEnded) {
        hydratedRouteKeyRef.current = routeKey;
        liveRequestRouteKeyRef.current = routeKey;
        return;
      }
      setRouteState(null, []);
      hydratedRouteKeyRef.current = routeKey;
      liveRequestRouteKeyRef.current = null;
      // Fall through to session creation below. We just reset the store so
      // liveSessionId is null — read fresh state to avoid stale-closure guards.
    }

    // Read authoritative store values — the closure may still hold stale references
    // from before setRouteState() was called above.
    const freshState = useChatStore.getState();

    if (freshState.liveSessionId && freshState.resumeSessionId === null && !freshState.sessionEnded) {
      liveRequestRouteKeyRef.current = routeKey;
      return;
    }

    if (liveRequestRouteKeyRef.current !== routeKey) {
      if (configQuery.isPending || configQuery.isFetching) {
        return;
      }
      const profiles = configQuery.data?.model_profiles ?? [];
      if (profiles.length === 0) {
        return;
      }
      const nextProfileId = resolveSavedProfileId(
        pendingProfileId
        ?? configQuery.data?.active_profile_id
        ?? profiles[0]?.id
        ?? null,
        profiles,
      );
      createSession(nextProfileId ? { profile_id: nextProfileId } : {});
      liveRequestRouteKeyRef.current = routeKey;
    }
  }, [
    awaitingBlankChat,
    createSession,
    configQuery.data,
    configQuery.isFetching,
    configQuery.isPending,
    liveSessionId,
    pendingProfileId,
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

  const modelProfiles = configQuery.data?.model_profiles ?? [];
  const routeProfileId = routeSessionId ? (activeSessionRecord?.profile_id ?? "") : "";
  const runtimeProfileId = runtime?.profile_id ?? "";
  const initialBlankProfileId =
    configQuery.data?.active_profile_id ?? modelProfiles[0]?.id ?? "";
  const selectedProfileId = pendingProfileId
    ?? (runtimeProfileId || (routeSessionId ? routeProfileId : initialBlankProfileId));
  const providerSupportsImages =
    runtime?.provider
      ? (configQuery.data?.options.provider_metadata[runtime.provider]?.supports_image_inputs
        ?? supportsImageInputs)
      : supportsImageInputs;
  const selectedSavedProfileId = resolveSavedProfileId(selectedProfileId, modelProfiles);
  const profileSelectorDisabled =
    modelProfiles.length === 0
    || !liveSessionId
    || !inputEnabled
    || sessionEnded
    || createSessionMutation.isPending
    || requestNewChatMutation.isPending
    || setChatProfileMutation.isPending
    || setActiveProfileMutation.isPending;

  const handleSubmit = async (payload: { text: string; images: File[] }) => {
    const { text, images } = payload;
    setInputWarnings([]);
    if (text.startsWith("/")) {
      await sendInputMutation.mutateAsync({
        text,
        file_paths: [],
        image_paths: [],
        image_upload_ids: [],
        profile_id: selectedSavedProfileId,
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
      profile_id: selectedSavedProfileId,
    });
  };

  const openBlankChat = async ({
    replace = false,
    awaitCreate = false,
    profileId = null,
  }: {
    replace?: boolean;
    awaitCreate?: boolean;
    profileId?: string | null;
  } = {}) => {
    const routeKey = "__new__";
    setAwaitingBlankChat(false);
    liveRequestRouteKeyRef.current = routeKey;
    navigate("/chat", { replace });
    setRouteState(null, []);
    hydratedRouteKeyRef.current = routeKey;
    if (awaitCreate) {
      await createSessionAsync(profileId ? { profile_id: profileId } : {});
      return;
    }
    createSession(profileId ? { profile_id: profileId } : {});
  };

  const transitionToBlankChat = async ({
    replace = false,
    awaitCreate = false,
  }: {
    replace?: boolean;
    awaitCreate?: boolean;
  } = {}) => {
    const currentLiveSessionId = liveSessionId;
    const nextProfileId = resolveSavedProfileId(
      configQuery.data?.active_profile_id ?? modelProfiles[0]?.id ?? null,
      modelProfiles,
    );
    setAwaitingBlankChat(true);

    if (currentLiveSessionId && !sessionEnded) {
      try {
        const session = await requestNewChatMutation.mutateAsync({
          liveSessionId: currentLiveSessionId,
          profileId: nextProfileId,
        });
        attachLiveSession({ ...session, resume_session_id: null }, false);
        navigate("/chat", { replace });
      } catch {
        await openBlankChat({ replace, awaitCreate, profileId: nextProfileId });
      }
    } else {
      await openBlankChat({ replace, awaitCreate, profileId: nextProfileId });
    }

    window.setTimeout(() => composerRef.current?.focus(), 100);
  };

  const handleProfileChange = async (nextProfileId: string) => {
    setPendingProfileId(nextProfileId);
    try {
      const nextConfigRevision = configQuery.data?.config_revision;
      if (!nextConfigRevision) {
        throw new Error("Settings are not loaded yet.");
      }
      await setActiveProfileMutation.mutateAsync({
        profileId: nextProfileId,
        configRevision: nextConfigRevision,
      });
      if (liveSessionId) {
        await setChatProfileMutation.mutateAsync({
          liveSessionId,
          profileId: nextProfileId,
        });
      }
      setPendingProfileId(null);
    } catch {
      setPendingProfileId(null);
    }
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
          <div className="chat-topbar__leading">
            <ConnectionBadge connection={connection} />
            <ProfileSelector
              selectedProfileId={selectedProfileId}
              modelProfiles={modelProfiles}
              isLoading={configQuery.isPending}
              disabled={profileSelectorDisabled}
              onChange={(id) => { void handleProfileChange(id); }}
            />
          </div>
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
        {setChatProfileMutation.error ? (
          <div className="banner banner--error">{setChatProfileMutation.error.message}</div>
        ) : null}
        {setActiveProfileMutation.error ? (
          <div className="banner banner--error">{setActiveProfileMutation.error.message}</div>
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
              supportsImageInputs={providerSupportsImages}
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

function resolveSavedProfileId(
  profileId: string | null | undefined,
  modelProfiles: ModelProfileView[],
): string | null {
  if (!profileId) {
    return null;
  }
  return modelProfiles.some((profile) => profile.id === profileId) ? profileId : null;
}

function ProfileSelector({
  selectedProfileId,
  modelProfiles,
  isLoading,
  disabled,
  onChange,
}: {
  selectedProfileId: string;
  modelProfiles: ModelProfileView[];
  isLoading: boolean;
  disabled: boolean;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(e: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  const selectedProfile = modelProfiles.find((p) => p.id === selectedProfileId);

  let triggerLabel: string;
  if (isLoading && modelProfiles.length === 0) {
    triggerLabel = "Loading\u2026";
  } else if (modelProfiles.length === 0) {
    triggerLabel = "No profiles";
  } else if (selectedProfile) {
    triggerLabel = selectedProfile.name;
  } else if (selectedProfileId) {
    triggerLabel = "Unavailable";
  } else {
    triggerLabel = "Select profile";
  }

  return (
    <div className={`profile-selector${open ? " is-open" : ""}`} ref={containerRef}>
      <button
        type="button"
        className="profile-selector__trigger"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Model profile: ${triggerLabel}`}
      >
        <svg className="profile-selector__icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <rect x="9" y="9" width="6" height="6" />
          <line x1="9" y1="2" x2="9" y2="4" />
          <line x1="15" y1="2" x2="15" y2="4" />
          <line x1="9" y1="20" x2="9" y2="22" />
          <line x1="15" y1="20" x2="15" y2="22" />
          <line x1="2" y1="9" x2="4" y2="9" />
          <line x1="2" y1="15" x2="4" y2="15" />
          <line x1="20" y1="9" x2="22" y2="9" />
          <line x1="20" y1="15" x2="22" y2="15" />
        </svg>
        <span className="profile-selector__name">{triggerLabel}</span>
        <svg className="profile-selector__chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && modelProfiles.length > 0 && (
        <div className="profile-selector__dropdown" role="listbox" aria-label="Model profiles">
          {modelProfiles.map((profile) => {
            const isSelected = profile.id === selectedProfileId;
            return (
              <button
                key={profile.id}
                type="button"
                role="option"
                aria-selected={isSelected}
                className={`profile-selector__option${isSelected ? " is-selected" : ""}`}
                onClick={() => {
                  onChange(profile.id);
                  setOpen(false);
                }}
              >
                <span className="profile-selector__option-check">
                  {isSelected && (
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="profile-selector__check" aria-hidden="true">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </span>
                <span className="profile-selector__option-body">
                  <span className="profile-selector__option-name">{profile.name}</span>
                  <span className="profile-selector__option-meta">
                    <span>{profile.provider.name}</span>
                    {profile.model && <><span className="profile-selector__dot" aria-hidden="true">·</span><span>{profile.model}</span></>}
                    {profile.reasoning_effort && <><span className="profile-selector__dot" aria-hidden="true">·</span><span>{profile.reasoning_effort}</span></>}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
