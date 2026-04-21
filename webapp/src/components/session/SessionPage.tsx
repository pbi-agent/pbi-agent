import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  createLiveSession,
  deleteSession,
  expandSessionInput,
  fetchConfigBootstrap,
  fetchLiveSessionDetail,
  fetchSessionDetail,
  fetchSessions,
  setActiveModelProfile,
  setLiveSessionProfile,
  submitSessionInput,
  uploadSessionImages,
} from "../../api";
import type { HistoryItem, ModelProfileView, SessionRecord, TimelineItem } from "../../types";
import {
  getLiveSessionKey,
  getSavedSessionKey,
  useSessionStore,
} from "../../store";
import { useLiveSessionEvents } from "../../hooks/useLiveSessionEvents";
import { ConnectionBadge } from "./ConnectionBadge";
import { DeleteSessionModal } from "./DeleteSessionModal";
import { RunHistory } from "./RunHistory";
import { SessionSidebar } from "./SessionSidebar";
import { SessionTimeline } from "./SessionTimeline";
import { UsageBar } from "./UsageBar";
import { Composer, type ComposerHandle } from "./Composer";

export function SessionPage({
  workspaceRoot,
  supportsImageInputs,
}: {
  workspaceRoot: string | undefined;
  supportsImageInputs: boolean;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const {
    sessionId: routeSessionId,
    liveSessionId: routeLiveSessionId,
  } = useParams<{ sessionId?: string; liveSessionId?: string }>();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inputWarnings, setInputWarnings] = useState<string[]>([]);
  const [pendingDeleteSession, setPendingDeleteSession] = useState<SessionRecord | null>(null);
  const [pendingProfileId, setPendingProfileId] = useState<string | null>(null);
  const composerRef = useRef<ComposerHandle>(null);
  const createRequestKeyRef = useRef<string | null>(null);

  const routeSessionKey = routeSessionId
    ? getSavedSessionKey(routeSessionId)
    : routeLiveSessionId
      ? getLiveSessionKey(routeLiveSessionId)
      : null;

  const activeSessionKey = useSessionStore((state) => {
    if (routeSessionId) {
      return state.sessionIndex[routeSessionId] ?? getSavedSessionKey(routeSessionId);
    }
    if (routeLiveSessionId) {
      return state.liveSessionIndex[routeLiveSessionId] ?? getLiveSessionKey(routeLiveSessionId);
    }
    return state.activeSessionKey;
  });
  const selectedRouteSessionKey =
    routeSessionId || routeLiveSessionId ? (activeSessionKey ?? routeSessionKey) : null;

  const sessionState = useSessionStore((state) =>
    selectedRouteSessionKey ? state.sessionsByKey[selectedRouteSessionKey] ?? null : null,
  );
  const setActiveSession = useSessionStore((state) => state.setActiveSession);
  const hydrateSavedSession = useSessionStore((state) => state.hydrateSavedSession);
  const attachLiveSession = useSessionStore((state) => state.attachLiveSession);
  const hydrateLiveSnapshot = useSessionStore((state) => state.hydrateLiveSnapshot);
  const updateRuntimeFromSession = useSessionStore((state) => state.updateRuntimeFromSession);

  useEffect(() => {
    setActiveSession(selectedRouteSessionKey);
  }, [selectedRouteSessionKey, setActiveSession]);

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

  const liveSessionDetailQuery = useQuery({
    queryKey: ["live-session", routeLiveSessionId],
    queryFn: () => fetchLiveSessionDetail(routeLiveSessionId!),
    enabled: Boolean(routeLiveSessionId),
    retry: false,
  });

  const configQuery = useQuery({
    queryKey: ["config-bootstrap"],
    queryFn: fetchConfigBootstrap,
    staleTime: 30_000,
  });

  const createSessionMutation = useMutation({
    mutationFn: createLiveSession,
    onSuccess: (session, variables) => {
      const requestSessionId =
        variables?.resume_session_id ?? variables?.session_id ?? null;
      const requestedKey = createRequestKeyRef.current
        ?? (requestSessionId
          ? getSavedSessionKey(requestSessionId)
          : getLiveSessionKey(session.live_session_id));
      const resolvedKey = attachLiveSession(requestedKey, session, {
        preserveItems: Boolean(requestSessionId),
      });
      if (!requestSessionId) {
        void navigate(`/sessions/live/${encodeURIComponent(session.live_session_id)}`, {
          replace: true,
        });
      } else if (resolvedKey !== requestedKey && session.session_id) {
        void navigate(`/sessions/${encodeURIComponent(session.session_id)}`, { replace: true });
      }
    },
  });

  const sendInputMutation = useMutation({
    mutationFn: (payload: {
      text: string;
      file_paths: string[];
      image_paths: string[];
      image_upload_ids: string[];
      profile_id?: string | null;
    }) => {
      if (!sessionState?.liveSessionId) throw new Error("No live session available.");
      return submitSessionInput(sessionState.liveSessionId, payload);
    },
    onSuccess: (session) => {
      if (selectedRouteSessionKey) {
        updateRuntimeFromSession(selectedRouteSessionKey, session);
      }
    },
  });

  const deleteSessionMutation = useMutation({
    mutationFn: deleteSession,
  });

  const setSessionProfileMutation = useMutation({
    mutationFn: ({
      liveSessionId,
      profileId,
    }: {
      liveSessionId: string;
      profileId: string | null;
    }) => setLiveSessionProfile(liveSessionId, profileId),
    onSuccess: (session) => {
      const targetKey = session.session_id
        ? getSavedSessionKey(session.session_id)
        : selectedRouteSessionKey;
      if (targetKey) {
        updateRuntimeFromSession(targetKey, session);
      }
      void client.invalidateQueries({ queryKey: ["sessions"] });
      if (session.session_id) {
        void client.invalidateQueries({ queryKey: ["session", session.session_id] });
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

  // Hydrate saved session items when session detail data arrives.
  // Skip hydration when a live session is already attached and has
  // items — even if the WebSocket is reconnecting.  Re-hydrating
  // during reconnection replaces WS-sourced items (item IDs like
  // "message-N") with API history items ("history-N"), then the WS
  // snapshot replay adds them again with their original IDs,
  // producing duplicates and flickering.
  useEffect(() => {
    if (!routeSessionId || !sessionDetailQuery.isSuccess) return;
    const sessionKey = getSavedSessionKey(routeSessionId);
    const existing = useSessionStore.getState().sessionsByKey[sessionKey];
    const skipHydration =
      existing?.liveSessionId
      && !existing.sessionEnded
      && existing.items.length > 0;
    if (!skipHydration) {
      const serverSeq =
        sessionDetailQuery.data.active_live_session?.last_event_seq;
      hydrateSavedSession(
        routeSessionId,
        sessionDetailQuery.data.history_items.map(mapHistoryItem),
        typeof serverSeq === "number" ? serverSeq : undefined,
      );
    }
    if (sessionDetailQuery.data.active_live_session) {
      attachLiveSession(sessionKey, sessionDetailQuery.data.active_live_session, {
        preserveItems: true,
      });
    }
  }, [
    attachLiveSession,
    hydrateSavedSession,
    routeSessionId,
    sessionDetailQuery.isSuccess,
    sessionDetailQuery.data,
  ]);

  // Create a new live session for a saved session when one doesn't exist yet.
  useEffect(() => {
    if (!routeSessionId || !sessionDetailQuery.isSuccess) return;
    if (sessionDetailQuery.data.active_live_session) return;
    if (sessionState?.liveSessionId && !sessionState.sessionEnded) return;
    if (createSessionMutation.isPending) return;
    createRequestKeyRef.current = getSavedSessionKey(routeSessionId);
    createSessionMutation.mutate({ resume_session_id: routeSessionId });
  }, [
    sessionState?.liveSessionId,
    sessionState?.sessionEnded,
    createSessionMutation,
    routeSessionId,
    sessionDetailQuery.isSuccess,
    sessionDetailQuery.data?.active_live_session,
  ]);

  useEffect(() => {
    if (!routeLiveSessionId || !liveSessionDetailQuery.isSuccess) return;
    const resolvedKey = hydrateLiveSnapshot(
      getLiveSessionKey(routeLiveSessionId),
      liveSessionDetailQuery.data.live_session,
      liveSessionDetailQuery.data.snapshot,
    );
    if (liveSessionDetailQuery.data.live_session.session_id) {
      void navigate(
        `/sessions/${encodeURIComponent(liveSessionDetailQuery.data.live_session.session_id)}`,
        { replace: true },
      );
      setActiveSession(resolvedKey);
    }
  }, [
    hydrateLiveSnapshot,
    liveSessionDetailQuery.isSuccess,
    liveSessionDetailQuery.data,
    navigate,
    routeLiveSessionId,
    setActiveSession,
  ]);

  useEffect(() => {
    if (routeSessionId || routeLiveSessionId) return;
    if (createSessionMutation.isPending) return;
    const profiles = configQuery.data?.model_profiles ?? [];
    if (profiles.length === 0) return;
    const profileId = resolveSavedProfileId(
      pendingProfileId ?? configQuery.data?.active_profile_id ?? profiles[0]?.id ?? null,
      profiles,
    );
    createRequestKeyRef.current = null;
    createSessionMutation.mutate(profileId ? { profile_id: profileId } : {});
  }, [
    configQuery.data,
    createSessionMutation,
    pendingProfileId,
    routeLiveSessionId,
    routeSessionId,
  ]);

  useEffect(() => {
    if (!routeLiveSessionId || !sessionState?.sessionId) return;
    void navigate(`/sessions/${encodeURIComponent(sessionState.sessionId)}`, { replace: true });
  }, [sessionState?.sessionId, navigate, routeLiveSessionId]);

  useEffect(() => {
    if (sessionState?.inputEnabled && sessionState.liveSessionId && !sessionState.sessionEnded) {
      composerRef.current?.focus();
    }
  }, [sessionState?.inputEnabled, sessionState?.liveSessionId, sessionState?.sessionEnded]);

  useEffect(() => {
    if (inputWarnings.length === 0) return undefined;
    const timeoutId = window.setTimeout(() => setInputWarnings([]), 5000);
    return () => window.clearTimeout(timeoutId);
  }, [inputWarnings]);

  useEffect(() => {
    const sessionId = sessionState?.sessionId;
    if (!sessionId) return;
    void client.invalidateQueries({ queryKey: ["sessions"] });
    void client.invalidateQueries({ queryKey: ["session", sessionId] });
  }, [sessionState?.sessionId, client]);

  useLiveSessionEvents(selectedRouteSessionKey, sessionState?.liveSessionId ?? null);

  const activeSessionRecord = useMemo(() => {
    if (!routeSessionId) return null;
    return (
      sessionDetailQuery.data?.session
      ?? sessionsQuery.data?.find((session) => session.session_id === routeSessionId)
      ?? {
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
      }
    );
  }, [routeSessionId, sessionDetailQuery.data?.session, sessionsQuery.data, workspaceRoot]);

  const modelProfiles = configQuery.data?.model_profiles ?? [];
  const routeProfileId = routeSessionId ? activeSessionRecord?.profile_id ?? "" : "";
  const runtimeProfileId = sessionState?.runtime?.profile_id ?? "";
  const initialBlankProfileId = configQuery.data?.active_profile_id ?? modelProfiles[0]?.id ?? "";
  const selectedProfileId =
    pendingProfileId ?? (runtimeProfileId || (routeSessionId ? routeProfileId : initialBlankProfileId));
  const selectedSavedProfileId = resolveSavedProfileId(selectedProfileId, modelProfiles);
  const providerSupportsImages =
    sessionState?.runtime?.provider
      ? (
          configQuery.data?.options.provider_metadata[sessionState.runtime.provider]?.supports_image_inputs
          ?? supportsImageInputs
        )
      : supportsImageInputs;
  const profileSelectorDisabled =
    modelProfiles.length === 0
    || !sessionState?.liveSessionId
    || !sessionState.inputEnabled
    || sessionState.sessionEnded
    || createSessionMutation.isPending
    || setSessionProfileMutation.isPending
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

    const expanded = await expandSessionInput(text);
    if (expanded.warnings.length > 0) {
      setInputWarnings(expanded.warnings);
    }
    const uploadedImageIds =
      images.length > 0 && sessionState?.liveSessionId
        ? (await uploadSessionImages(sessionState.liveSessionId, images)).map((image) => image.upload_id)
        : [];
    await sendInputMutation.mutateAsync({
      text: expanded.text,
      file_paths: expanded.file_paths,
      image_paths: Array.from(new Set(expanded.image_paths)),
      image_upload_ids: uploadedImageIds,
      profile_id: selectedSavedProfileId,
    });
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
      if (sessionState?.liveSessionId) {
        await setSessionProfileMutation.mutateAsync({
          liveSessionId: sessionState.liveSessionId,
          profileId: nextProfileId,
        });
      }
    } finally {
      setPendingProfileId(null);
    }
  };

  const handleNewSession = () => {
    setSidebarOpen(false);
    createRequestKeyRef.current = null;
    void navigate("/sessions");
  };

  const handleDeleteSession = async () => {
    if (!pendingDeleteSession) return;
    const deletingActive = pendingDeleteSession.session_id === routeSessionId;
    await deleteSessionMutation.mutateAsync(pendingDeleteSession.session_id);
    client.setQueryData<SessionRecord[] | undefined>(["sessions"], (sessions) =>
      (sessions ?? []).filter((session) => session.session_id !== pendingDeleteSession.session_id),
    );
    setPendingDeleteSession(null);
    await client.invalidateQueries({ queryKey: ["sessions"] });
    if (deletingActive) {
      void navigate("/sessions", { replace: true });
    }
  };

  const canDeleteActiveSession = Boolean(routeSessionId && activeSessionRecord);
  const isDeleteBusy = deleteSessionMutation.isPending || createSessionMutation.isPending;
  const sessionDetailError = routeSessionId ? sessionDetailQuery.error : liveSessionDetailQuery.error;
  const sessionNotFound =
    sessionDetailError instanceof ApiError && sessionDetailError.status === 404;
  const sessionDetailLoadError =
    (routeSessionId || routeLiveSessionId) && sessionDetailError && !sessionNotFound
      ? "Unable to load this session right now."
      : null;

  return (
    <section className={`session-layout ${sidebarOpen ? "session-layout--sidebar-open" : ""}`}>
      <div className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}>
        <SessionSidebar
          sessions={sessionsQuery.data ?? []}
          isLoading={sessionsQuery.isLoading}
          activeSessionId={routeSessionId ?? sessionState?.sessionId ?? null}
          workspaceRoot={workspaceRoot}
          onNewSession={handleNewSession}
          onResumeSession={(sessionId) => {
            void navigate(`/sessions/${encodeURIComponent(sessionId)}`);
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

      <div className="session-panel">
        <div className="session-topbar">
          <div className="session-topbar__leading">
            <ConnectionBadge connection={sessionState?.connection ?? "disconnected"} />
            <ProfileSelector
              selectedProfileId={selectedProfileId}
              modelProfiles={modelProfiles}
              isLoading={configQuery.isPending}
              disabled={profileSelectorDisabled}
              onChange={(id) => {
                void handleProfileChange(id);
              }}
            />
          </div>
          <div className="session-topbar__actions">
            <UsageBar
              sessionUsage={sessionState?.sessionUsage ?? null}
              turnUsage={sessionState?.turnUsage ?? null}
            />
            {routeSessionId ? (
              <RunHistory sessionId={routeSessionId} />
            ) : null}
            {canDeleteActiveSession ? (
              <button
                type="button"
                className="btn btn--ghost btn--icon btn--danger"
                title="Delete session"
                onClick={() => {
                  if (activeSessionRecord) {
                    deleteSessionMutation.reset();
                    setPendingDeleteSession(activeSessionRecord);
                  }
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
        {sessionState?.fatalError ? (
          <div className="banner banner--error">{sessionState.fatalError}</div>
        ) : null}
        {createSessionMutation.error ? (
          <div className="banner banner--error">{createSessionMutation.error.message}</div>
        ) : null}
        {setSessionProfileMutation.error ? (
          <div className="banner banner--error">{setSessionProfileMutation.error.message}</div>
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
              {sessionDetailError instanceof Error
                ? sessionDetailError.message
                : "This session does not exist in the current workspace."}
            </div>
            <button
              type="button"
              className="btn btn--primary empty-state__action"
              onClick={handleNewSession}
            >
              Start new session
            </button>
          </div>
        ) : (
          <>
            <SessionTimeline
              items={sessionState?.items ?? []}
              itemsVersion={sessionState?.itemsVersion ?? 0}
              subAgents={sessionState?.subAgents ?? {}}
              connection={sessionState?.connection ?? "disconnected"}
              waitMessage={sessionState?.waitMessage ?? null}
            />
            <Composer
              ref={composerRef}
              inputEnabled={sessionState?.inputEnabled ?? false}
              sessionEnded={sessionState?.sessionEnded ?? false}
              liveSessionId={sessionState?.liveSessionId ?? null}
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
  candidateId: string | null,
  modelProfiles: ModelProfileView[],
): string | null {
  return candidateId && modelProfiles.some((profile) => profile.id === candidateId)
    ? candidateId
    : null;
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
  onChange: (profileId: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      if (
        containerRef.current
        && event.target instanceof Node
        && !containerRef.current.contains(event.target)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [isOpen]);

  const selectedProfile = modelProfiles.find((profile) => profile.id === selectedProfileId);
  const label = isLoading && modelProfiles.length === 0
    ? "Loading…"
    : modelProfiles.length === 0
      ? "No profiles"
      : selectedProfile
        ? selectedProfile.name
        : selectedProfileId
          ? "Unavailable"
          : "Select profile";

  return (
    <div className={`profile-selector${isOpen ? " is-open" : ""}`} ref={containerRef}>
      <button
        type="button"
        className="profile-selector__trigger"
        onClick={() => setIsOpen((value) => !value)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={`Model profile: ${label}`}
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
        <span className="profile-selector__name">{label}</span>
        <svg className="profile-selector__chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && modelProfiles.length > 0 ? (
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
                  setIsOpen(false);
                }}
              >
                <span className="profile-selector__option-check">
                  {isSelected ? (
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="profile-selector__check" aria-hidden="true">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : null}
                </span>
                <span className="profile-selector__option-body">
                  <span className="profile-selector__option-name">{profile.name}</span>
                  <span className="profile-selector__option-meta">
                    <span>{profile.provider.name}</span>
                    {profile.model ? (
                      <>
                        <span className="profile-selector__dot" aria-hidden="true">·</span>
                        <span>{profile.model}</span>
                      </>
                    ) : null}
                    {profile.reasoning_effort ? (
                      <>
                        <span className="profile-selector__dot" aria-hidden="true">·</span>
                        <span>{profile.reasoning_effort}</span>
                      </>
                    ) : null}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
