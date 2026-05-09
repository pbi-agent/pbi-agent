import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangleIcon,
  ArrowLeftIcon,
  CheckIcon,
  ChevronDownIcon,
  CpuIcon,
  MessageCircleQuestionMark,
} from "lucide-react";
import { AppSidebarLayout } from "../AppSidebar";
import {
  ApiError,
  createSession,
  deleteSession,
  expandSessionInput,
  fetchConfigBootstrap,
  fetchSessionDetail,
  fetchSessions,
  interruptSession,
  runSessionShellCommand,
  sendSessionMessage,
  setActiveModelProfile,
  setSessionProfile,
  submitSessionQuestionResponse,
  updateSession,
  uploadSavedSessionImages,
} from "../../api";
import type {
  HistoryItem,
  LiveSession,
  ModelProfileView,
  SessionDetailPayload,
  SessionRecord,
  TimelineItem,
  LiveSessionSnapshot,
  ProcessingState,
  UserQuestionAnswer,
} from "../../types";
import {
  getSavedSessionKey,
  useSessionStore,
} from "../../store";
import { useSessionEvents } from "../../hooks/useSessionEvents";
import { ConnectionBadge } from "./ConnectionBadge";
import { DeleteSessionModal } from "./DeleteSessionModal";
import { RunHistory } from "./RunHistory";
import { SessionSidebar } from "./SessionSidebar";
import { SessionTimeline } from "./SessionTimeline";
import { UsageBar } from "./UsageBar";
import { UserQuestionsPanel } from "./UserQuestionsPanel";
import { Composer, type ComposerHandle } from "./Composer";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { EmptyState } from "../shared/EmptyState";
import { Toggle } from "../ui/toggle";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

export function SessionPage({
  workspaceRoot,
  supportsImageInputs,
}: {
  workspaceRoot: string | undefined;
  supportsImageInputs: boolean;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const { sessionId: routeSessionId, subAgentId: routeSubAgentId } = useParams<{
    sessionId?: string;
    subAgentId?: string;
  }>();
  const isSubAgentRoute = Boolean(routeSessionId && routeSubAgentId);
  const [inputWarnings, setInputWarnings] = useState<string[]>([]);
  const [pendingDeleteSession, setPendingDeleteSession] = useState<SessionRecord | null>(null);
  const [pendingProfileId, setPendingProfileId] = useState<string | null>(null);
  const [interactiveMode, setInteractiveMode] = useState(() =>
    window.localStorage.getItem("pbi-agent.interactive-mode") === "true",
  );
  const composerRef = useRef<ComposerHandle>(null);
  const submitInFlightRef = useRef(false);
  const [directSubmitPending, setDirectSubmitPending] = useState(false);

  const routeSessionKey = routeSessionId
    ? getSavedSessionKey(routeSessionId)
    : null;

  const activeSessionKey = useSessionStore((state) => {
    if (routeSessionId) {
      return state.sessionIndex[routeSessionId] ?? getSavedSessionKey(routeSessionId);
    }
    return state.activeSessionKey;
  });
  const selectedRouteSessionKey =
    routeSessionId ? (activeSessionKey ?? routeSessionKey) : null;

  const sessionState = useSessionStore((state) =>
    selectedRouteSessionKey ? state.sessionsByKey[selectedRouteSessionKey] ?? null : null,
  );
  const setActiveSession = useSessionStore((state) => state.setActiveSession);
  const hydrateSavedSession = useSessionStore((state) => state.hydrateSavedSession);
  const attachLiveSession = useSessionStore((state) => state.attachLiveSession);
  const hydrateLiveSnapshot = useSessionStore((state) => state.hydrateLiveSnapshot);
  const updateRuntimeFromSession = useSessionStore((state) => state.updateRuntimeFromSession);
  const consumeRestoredInput = useSessionStore((state) => state.consumeRestoredInput);

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

  const configQuery = useQuery({
    queryKey: ["config-bootstrap"],
    queryFn: fetchConfigBootstrap,
    staleTime: 30_000,
  });

  const createSessionMutation = useMutation({
    mutationFn: createSession,
    onSuccess: (session) => {
      hydrateSavedSession(session.session_id, []);
      void client.invalidateQueries({ queryKey: ["sessions"] });
      void navigate(`/sessions/${encodeURIComponent(session.session_id)}`, { replace: true });
    },
  });

  const sendInputMutation = useMutation({
    mutationFn: (payload: {
      text: string;
      file_paths: string[];
      image_paths: string[];
      image_upload_ids: string[];
      profile_id?: string | null;
      interactive_mode?: boolean;
    }) => {
      const sessionId = routeSessionId ?? sessionState?.sessionId;
      if (!sessionId) throw new Error("No session available.");
      return sendSessionMessage(sessionId, payload);
    },
    onSuccess: (session) => {
      if (!selectedRouteSessionKey) return;
      if (routeSessionId) {
        attachLiveSession(selectedRouteSessionKey, session, {
          preserveItems: true,
          preserveEventCursor: true,
        });
        return;
      }
      updateRuntimeFromSession(selectedRouteSessionKey, session);
    },
  });

  const questionResponseMutation = useMutation({
    mutationFn: (answers: UserQuestionAnswer[]) => {
      const sessionId = routeSessionId ?? sessionState?.sessionId;
      if (!sessionId || !sessionState?.pendingUserQuestions) {
        throw new Error("No pending assistant questions.");
      }
      const payload = {
        prompt_id: sessionState.pendingUserQuestions.prompt_id,
        answers,
      };
      return submitSessionQuestionResponse(sessionId, payload);
    },
    onSuccess: (session) => {
      if (selectedRouteSessionKey) {
        updateRuntimeFromSession(selectedRouteSessionKey, session);
      }
    },
  });

  const shellCommandMutation = useMutation({
    mutationFn: (payload: { command: string }) => {
      const sessionId = routeSessionId ?? sessionState?.sessionId;
      if (!sessionId) throw new Error("No session available.");
      return runSessionShellCommand(sessionId, payload);
    },
    onSuccess: (session) => {
      if (selectedRouteSessionKey) {
        updateRuntimeFromSession(selectedRouteSessionKey, session);
      }
    },
  });

  const interruptMutation = useMutation({
    mutationFn: () => {
      const sessionId = routeSessionId ?? sessionState?.sessionId;
      if (!sessionId) throw new Error("No session available.");
      return interruptSession(sessionId);
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
        (detail) => detail ? { ...detail, session: updatedSession } : detail,
      );
      void client.invalidateQueries({ queryKey: ["sessions"] });
      void client.invalidateQueries({ queryKey: ["bootstrap"] });
      void client.invalidateQueries({ queryKey: ["session", updatedSession.session_id] });
    },
  });

  const setSessionProfileMutation = useMutation({
    mutationFn: ({
      sessionId,
      profileId,
    }: {
      sessionId?: string | null;
      profileId: string | null;
    }) => {
      if (sessionId) return setSessionProfile(sessionId, profileId);
      throw new Error("No session available.");
    },
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

  useEffect(() => {
    window.localStorage.setItem("pbi-agent.interactive-mode", String(interactiveMode));
  }, [interactiveMode]);

  useEffect(() => {
    if (isSubAgentRoute) return undefined;

    const handleInteractiveShortcut = (event: KeyboardEvent) => {
      if (
        event.key !== "Tab"
        || !event.shiftKey
        || event.repeat
        || event.ctrlKey
        || event.metaKey
        || event.altKey
      ) {
        return;
      }

      event.preventDefault();
      setInteractiveMode((current) => !current);
    };

    window.addEventListener("keydown", handleInteractiveShortcut, true);
    return () => {
      window.removeEventListener("keydown", handleInteractiveShortcut, true);
    };
  }, [isSubAgentRoute]);

  useEffect(() => {
    const handleNewSessionShortcut = (event: KeyboardEvent) => {
      if (
        event.key.toLowerCase() !== "o"
        || !event.ctrlKey
        || !event.shiftKey
        || event.repeat
        || event.metaKey
        || event.altKey
      ) {
        return;
      }

      event.preventDefault();
      void navigate("/sessions");
    };

    window.addEventListener("keydown", handleNewSessionShortcut, true);
    return () => {
      window.removeEventListener("keydown", handleNewSessionShortcut, true);
    };
  }, [navigate]);

  // Hydrate saved session items when session detail data arrives.
  // Skip hydration when a live session is already attached and has
  // items — even if the event stream is reconnecting. Re-hydrating
  // during reconnection can briefly replace live items before replay
  // catches up, producing duplicates and flickering.
  useEffect(() => {
    if (!routeSessionId || !sessionDetailQuery.isSuccess) return;
    const sessionKey = getSavedSessionKey(routeSessionId);
    const existing = useSessionStore.getState().sessionsByKey[sessionKey];
    const hasServerLiveSource = Boolean(
      sessionDetailQuery.data.active_live_session
      || sessionDetailQuery.data.active_run
      || sessionDetailQuery.data.timeline,
    );
    const skipHydration =
      hasServerLiveSource
      && existing?.liveSessionId
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
    const snapshotSession =
      sessionDetailQuery.data.active_live_session
      ?? sessionDetailQuery.data.active_run
      ?? timelineSessionFromDetail(sessionDetailQuery.data);
    if (snapshotSession) {
      const timeline = sessionDetailQuery.data.timeline;
      if (timeline) {
        const hasActiveTimelineSource = Boolean(
          sessionDetailQuery.data.active_live_session
          || sessionDetailQuery.data.active_run,
        );
        const displayTimeline = timelineForDisplay(sessionDetailQuery.data, timeline);
        hydrateLiveSnapshot(
          sessionKey,
          snapshotSession,
          hasActiveTimelineSource
            ? displayTimeline
            : { ...displayTimeline, session_ended: true },
        );
      } else {
        attachLiveSession(sessionKey, snapshotSession, {
          preserveItems: true,
        });
      }
    }
  }, [
    attachLiveSession,
    hydrateLiveSnapshot,
    hydrateSavedSession,
    routeSessionId,
    sessionDetailQuery.isSuccess,
    sessionDetailQuery.data,
  ]);

  const composerInputEnabled = !isSubAgentRoute && Boolean(
    (!routeSessionId && !sessionState)
    || (routeSessionId && !sessionState?.liveSessionId && !sessionState?.pendingUserQuestions)
    || (sessionState?.inputEnabled && !sessionState.pendingUserQuestions),
  );
  const composerCanStartRun = Boolean(!routeSessionId || (routeSessionId && !sessionState?.liveSessionId));
  const rawConnection = sessionState?.connection ?? "disconnected";
  const topbarConnection = composerInputEnabled && (rawConnection === "disconnected" || rawConnection === "connecting")
    ? "ready"
    : rawConnection;
  const recoveryNotice = rawConnection === "reconnecting"
    ? "Connection lost. Reconnecting to the live stream..."
    : rawConnection === "recovering"
      ? "Recovering the session from the latest snapshot..."
      : null;
  const recoveryFailed = rawConnection === "recovery_failed"
    ? "Unable to recover the live stream. Refresh the session to reload the latest snapshot."
    : null;

  useEffect(() => {
    if (composerInputEnabled && !sessionState?.sessionEnded) {
      composerRef.current?.focus();
    }
  }, [composerInputEnabled, sessionState?.sessionEnded]);

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

  useSessionEvents(
    selectedRouteSessionKey,
    routeSessionId ?? null,
    sessionState?.liveSessionId ?? null,
  );

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
    isSubAgentRoute
    || modelProfiles.length === 0
    || Boolean(sessionState && !composerInputEnabled)
    || createSessionMutation.isPending
    || setSessionProfileMutation.isPending
    || setActiveProfileMutation.isPending;

  const ensureDraftSession = async (): Promise<string> => {
    const existingSessionId = routeSessionId ?? sessionState?.sessionId;
    if (existingSessionId) return existingSessionId;
    const created = await createSessionMutation.mutateAsync({
      ...(selectedSavedProfileId ? { profile_id: selectedSavedProfileId } : {}),
    });
    return created.session_id;
  };

  const uploadImagesForCurrentSession = async (images: File[], sessionId: string) => {
    if (images.length === 0) return [];
    return (await uploadSavedSessionImages(sessionId, images)).map(
      (image) => image.upload_id,
    );
  };

  const handleSubmit = async (payload: { text: string; images: File[] }) => {
    if (submitInFlightRef.current) return;
    submitInFlightRef.current = true;
    setDirectSubmitPending(true);
    try {
    const { text, images } = payload;
    setInputWarnings([]);
    if (text.startsWith("!")) {
      if (images.length > 0) {
        throw new Error("Shell commands cannot include image attachments.");
      }
      const command = text.slice(1).trim();
      if (!command) {
        throw new Error("Shell command must be a non-empty string.");
      }
      const sessionId = await ensureDraftSession();
      if (!routeSessionId) {
        void navigate(`/sessions/${encodeURIComponent(sessionId)}`, { replace: true });
      }
      const session = await runSessionShellCommand(sessionId, { command });
      attachLiveSession(getSavedSessionKey(sessionId), session, {
        preserveItems: true,
        preserveEventCursor: true,
      });
      return;
    }
    if (text.startsWith("/")) {
      const sessionId = await ensureDraftSession();
      const uploadedImageIds = await uploadImagesForCurrentSession(images, sessionId);
      const session = await sendSessionMessage(sessionId, {
        text,
        file_paths: [],
        image_paths: [],
        image_upload_ids: uploadedImageIds,
        profile_id: selectedSavedProfileId,
        interactive_mode: interactiveMode,
      });
      attachLiveSession(getSavedSessionKey(sessionId), session, {
        preserveItems: true,
        preserveEventCursor: true,
      });
      if (!routeSessionId) {
        void navigate(`/sessions/${encodeURIComponent(sessionId)}`, { replace: true });
      }
      return;
    }

    const expanded = await expandSessionInput(text);
    if (expanded.warnings.length > 0) {
      setInputWarnings(expanded.warnings);
    }
    const sessionId = await ensureDraftSession();
    const uploadedImageIds = await uploadImagesForCurrentSession(images, sessionId);
    const session = await sendSessionMessage(sessionId, {
      text: expanded.text,
      file_paths: expanded.file_paths,
      image_paths: Array.from(new Set(expanded.image_paths)),
      image_upload_ids: uploadedImageIds,
      profile_id: selectedSavedProfileId,
      interactive_mode: interactiveMode,
    });
    attachLiveSession(getSavedSessionKey(sessionId), session, {
      preserveItems: true,
      preserveEventCursor: true,
    });
    if (!routeSessionId) {
      void navigate(`/sessions/${encodeURIComponent(sessionId)}`, { replace: true });
    }
    } finally {
      submitInFlightRef.current = false;
      setDirectSubmitPending(false);
    }
  };

  const handleProfileChange = async (nextProfileId: string) => {
    setPendingProfileId(nextProfileId);
    try {
      const sessionId = routeSessionId ?? sessionState?.sessionId ?? null;
      if (sessionId) {
        await setSessionProfileMutation.mutateAsync({
          sessionId,
          profileId: nextProfileId,
        });
        return;
      }
      const nextConfigRevision = configQuery.data?.config_revision;
      if (!nextConfigRevision) {
        throw new Error("Settings are not loaded yet.");
      }
      await setActiveProfileMutation.mutateAsync({
        profileId: nextProfileId,
        configRevision: nextConfigRevision,
      });
    } finally {
      setPendingProfileId(null);
    }
  };

  const handleNewSession = () => {
    void navigate("/sessions");
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
    client.setQueryData<SessionRecord[] | undefined>(["sessions"], (sessions) =>
      (sessions ?? []).filter((session) => session.session_id !== pendingDeleteSession.session_id),
    );
    setPendingDeleteSession(null);
    await client.invalidateQueries({ queryKey: ["sessions"] });
    if (deletingActive) {
      void navigate("/sessions", { replace: true });
    }
  };

  const canInterruptActiveTurn = Boolean(
    !isSubAgentRoute
    && sessionState?.liveSessionId
    && !sessionState.sessionEnded
    && sessionState.processing?.active
    && !sessionState.inputEnabled,
  );
  const isDeleteBusy = deleteSessionMutation.isPending || createSessionMutation.isPending;
  const sessionDetailError = routeSessionId ? sessionDetailQuery.error : null;
  const sessionNotFound =
    sessionDetailError instanceof ApiError && sessionDetailError.status === 404;
  const sessionDetailLoadError =
    routeSessionId && sessionDetailError && !sessionNotFound
      ? "Unable to load this session right now."
      : null;
  const selectedSubAgent = isSubAgentRoute && routeSubAgentId
    ? sessionState?.subAgents[routeSubAgentId] ?? null
    : null;
  const selectedSubAgentIsRunning = selectedSubAgent?.status === "running";
  const displayedItems = useMemo(
    () => isSubAgentRoute && routeSubAgentId
      ? (sessionState?.items ?? []).filter((item) => item.subAgentId === routeSubAgentId)
      : sessionState?.items ?? [],
    [isSubAgentRoute, routeSubAgentId, sessionState?.items],
  );
  const displayedSubAgents = useMemo(
    () => isSubAgentRoute && routeSubAgentId
      ? {
          [routeSubAgentId]: selectedSubAgent ?? {
            title: routeSubAgentId,
            status: "completed",
          },
        }
      : sessionState?.subAgents ?? {},
    [isSubAgentRoute, routeSubAgentId, selectedSubAgent, sessionState?.subAgents],
  );
  const latestDisplayedItem = displayedItems.at(-1);
  const selectedSubAgentHasFinalResponse =
    latestDisplayedItem?.kind === "message" && latestDisplayedItem.role === "assistant";
  const showSelectedSubAgentProcessing =
    selectedSubAgentIsRunning && !selectedSubAgentHasFinalResponse;
  const displayedProcessing: ProcessingState | null = isSubAgentRoute
    ? showSelectedSubAgentProcessing
      ? sessionState?.processing ?? null
      : null
    : sessionState?.processing ?? null;
  const displayedWaitMessage = isSubAgentRoute && !showSelectedSubAgentProcessing
    ? null
    : sessionState?.waitMessage ?? null;

  const sessionListPanel = (
    <SessionSidebar
      sessions={sessionsQuery.data ?? []}
      isLoading={sessionsQuery.isLoading}
      activeSessionId={routeSessionId ?? sessionState?.sessionId ?? null}
      onNewSession={handleNewSession}
      onResumeSession={(sessionId) => {
        void navigate(`/sessions/${encodeURIComponent(sessionId)}`);
      }}
      onUpdateSession={handleUpdateSessionTitle}
      onDeleteSession={(session) => {
        deleteSessionMutation.reset();
        setPendingDeleteSession(session);
      }}
    />
  );

  return (
    <AppSidebarLayout contextPanel={sessionListPanel}>
      <section
        className="session-panel-wrapper"
        data-debug-session-key={selectedRouteSessionKey ?? undefined}
        data-debug-session-id={sessionState?.sessionId ?? undefined}
        data-debug-live-session-id={sessionState?.liveSessionId ?? undefined}
        data-debug-event-cursor={sessionState?.lastEventSeq ?? undefined}
        data-debug-connection={sessionState?.connection ?? undefined}
      >
        <div className="session-panel">
        <div className="session-topbar">
          <div className="session-topbar__leading">
            <ConnectionBadge connection={topbarConnection} />
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
            {!isSubAgentRoute ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Toggle
                    type="button"
                    variant="outline"
                    size="sm"
                    className="session-topbar-control session-interactive-toggle"
                    pressed={interactiveMode}
                    aria-label={
                      interactiveMode ? "Disable interactive mode" : "Enable interactive mode"
                    }
                    onPressedChange={setInteractiveMode}
                  >
                    <MessageCircleQuestionMark aria-hidden="true" />
                  </Toggle>
                </TooltipTrigger>
                <TooltipContent side="bottom" align="end">
                  {interactiveMode
                    ? "Interactive mode enabled. Press Maj+Tab / Shift+Tab to disable."
                    : "Let the agent ask questions and offer choices. Press Maj+Tab / Shift+Tab to enable."}
                </TooltipContent>
              </Tooltip>
            ) : null}
            {routeSessionId && !isSubAgentRoute ? (
              <RunHistory sessionId={routeSessionId} />
            ) : null}
            <UsageBar
              compactThreshold={sessionState?.runtime?.compact_threshold ?? null}
              usage={sessionState?.sessionUsage ?? sessionState?.turnUsage?.usage ?? null}
            />
          </div>
        </div>

        {inputWarnings.length > 0 ? (
          <Alert className="banner banner--notice">
            <AlertTriangleIcon />
            <AlertDescription>{inputWarnings.join(" ")}</AlertDescription>
          </Alert>
        ) : null}
        {recoveryNotice ? (
          <Alert className="banner banner--notice">
            <AlertTriangleIcon />
            <AlertDescription>{recoveryNotice}</AlertDescription>
          </Alert>
        ) : null}
        {recoveryFailed ? (
          <Alert variant="destructive" className="banner banner--error">
            <AlertTriangleIcon />
            <AlertDescription>{recoveryFailed}</AlertDescription>
          </Alert>
        ) : null}
        {sessionState?.fatalError ? (
          <Alert variant="destructive" className="banner banner--error">
            <AlertTriangleIcon />
            <AlertDescription>{sessionState.fatalError}</AlertDescription>
          </Alert>
        ) : null}
        {createSessionMutation.error ? (
          <Alert variant="destructive" className="banner banner--error">
            <AlertTriangleIcon />
            <AlertDescription>{createSessionMutation.error.message}</AlertDescription>
          </Alert>
        ) : null}
        {setSessionProfileMutation.error ? (
          <Alert variant="destructive" className="banner banner--error">
            <AlertTriangleIcon />
            <AlertDescription>{setSessionProfileMutation.error.message}</AlertDescription>
          </Alert>
        ) : null}
        {setActiveProfileMutation.error ? (
          <Alert variant="destructive" className="banner banner--error">
            <AlertTriangleIcon />
            <AlertDescription>{setActiveProfileMutation.error.message}</AlertDescription>
          </Alert>
        ) : null}
        {!isSubAgentRoute && interruptMutation.error ? (
          <Alert variant="destructive" className="banner banner--error">
            <AlertTriangleIcon />
            <AlertDescription>{interruptMutation.error.message}</AlertDescription>
          </Alert>
        ) : null}
        {sessionDetailLoadError ? (
          <Alert variant="destructive" className="banner banner--error">
            <AlertTriangleIcon />
            <AlertDescription>{sessionDetailLoadError}</AlertDescription>
          </Alert>
        ) : null}

        {sessionNotFound ? (
          <EmptyState
            title="Session not found"
            description={
              sessionDetailError instanceof Error
                ? sessionDetailError.message
                : "This session does not exist in the current workspace."
            }
            action={
              <Button type="button" onClick={handleNewSession}>
                Start new session
              </Button>
            }
          />
        ) : (
          <>
            <SessionTimeline
              items={displayedItems}
              itemsVersion={sessionState?.itemsVersion ?? 0}
              subAgents={displayedSubAgents}
              connection={sessionState?.connection ?? "disconnected"}
              waitMessage={displayedWaitMessage}
              processing={displayedProcessing}
              parentSessionId={routeSessionId ?? sessionState?.sessionId ?? undefined}
              showSubAgentCards={!isSubAgentRoute}
            />
            {!isSubAgentRoute && sessionState?.pendingUserQuestions ? (
              <UserQuestionsPanel
                prompt={sessionState.pendingUserQuestions}
                isSubmitting={questionResponseMutation.isPending}
                errorMessage={questionResponseMutation.error?.message ?? null}
                onSubmit={async (answers) => {
                  await questionResponseMutation.mutateAsync(answers);
                }}
              />
            ) : null}
            {isSubAgentRoute && routeSessionId ? (
              <div className="session-readonly-footer">
                <Button
                  type="button"
                  variant="outline"
                  className="session-readonly-footer__button"
                  asChild
                >
                  <Link to={`/sessions/${encodeURIComponent(routeSessionId)}`}>
                    <ArrowLeftIcon data-icon="inline-start" aria-hidden="true" />
                    Back to main session
                  </Link>
                </Button>
              </div>
            ) : (
              <Composer
                ref={composerRef}
                inputEnabled={composerInputEnabled}
                sessionEnded={sessionState?.sessionEnded ?? false}
                liveSessionId={sessionState?.liveSessionId ?? null}
                canCreateSession={composerCanStartRun}
                supportsImageInputs={providerSupportsImages}
                interactiveMode={interactiveMode}
                isSubmitting={directSubmitPending || sendInputMutation.isPending || shellCommandMutation.isPending}
                onSubmit={handleSubmit}
                isProcessing={Boolean(sessionState?.processing?.active)}
                canInterrupt={canInterruptActiveTurn}
                isInterrupting={interruptMutation.isPending}
                restoredInput={sessionState?.restoredInput ?? null}
                onRestoredInputConsumed={() => {
                  if (selectedRouteSessionKey) {
                    consumeRestoredInput(selectedRouteSessionKey);
                  }
                }}
                onInterrupt={() => {
                  interruptMutation.mutate();
                }}
              />
            )}
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
    </AppSidebarLayout>
  );
}

function mapHistoryItem(item: HistoryItem): TimelineItem {
  return {
    kind: "message",
    itemId: item.item_id,
    messageId: item.message_id,
    partIds: item.part_ids,
    role: item.role,
    content: item.content,
    filePaths: item.file_paths,
    imageAttachments: item.image_attachments,
    markdown: item.markdown,
  };
}

function historyItemToSnapshotItem(item: HistoryItem): Record<string, unknown> {
  return {
    kind: "message",
    itemId: item.item_id,
    message_id: item.message_id,
    part_ids: item.part_ids,
    role: item.role,
    content: item.content,
    file_paths: item.file_paths,
    image_attachments: item.image_attachments,
    markdown: item.markdown,
    created_at: item.created_at,
  };
}

function messageSignature(item: Record<string, unknown>): string | null {
  if (item.kind !== "message") return null;
  const role = typeof item.role === "string" ? item.role : "";
  const content = typeof item.content === "string" ? item.content : "";
  const filePaths = Array.isArray(item.file_paths) ? item.file_paths : [];
  const imageAttachments = Array.isArray(item.image_attachments) ? item.image_attachments : [];
  return JSON.stringify([role, content, filePaths, imageAttachments]);
}

function persistedMessageId(item: Record<string, unknown>): string | null {
  if (item.kind !== "message") return null;
  return typeof item.message_id === "string"
    ? item.message_id
    : typeof item.messageId === "string"
      ? item.messageId
      : null;
}

function snapshotItemId(item: Record<string, unknown>): string {
  return typeof item.itemId === "string"
    ? item.itemId
    : typeof item.item_id === "string"
      ? item.item_id
      : "";
}

function isHistoricalSnapshotMessage(item: Record<string, unknown>): boolean {
  return item.kind === "message"
    && (item.historical === true || snapshotItemId(item).startsWith("history-"));
}

function timelineForDisplay(
  detail: SessionDetailPayload,
  timeline: LiveSessionSnapshot,
): LiveSessionSnapshot {
  const activeTimeline = Boolean(
    !timeline.session_ended && (detail.active_live_session || detail.active_run),
  );
  const dormantTimeline = !activeTimeline;
  if ((!activeTimeline && !dormantTimeline) || detail.history_items.length === 0) {
    return timeline;
  }

  const historyItems = detail.history_items.map(historyItemToSnapshotItem);
  const historySignatureCounts = new Map<string, number>();
  for (const item of historyItems) {
    const signature = messageSignature(item);
    if (signature) {
      historySignatureCounts.set(signature, (historySignatureCounts.get(signature) ?? 0) + 1);
    }
  }
  const snapshotSignatureCounts = new Map<string, number>();
  for (const item of timeline.items) {
    if (persistedMessageId(item) && !isHistoricalSnapshotMessage(item)) continue;
    const signature = messageSignature(item);
    if (signature) {
      snapshotSignatureCounts.set(signature, (snapshotSignatureCounts.get(signature) ?? 0) + 1);
    }
  }
  const historyMessageIds = new Set(
    historyItems.flatMap((item) => {
      const messageId = persistedMessageId(item);
      return messageId ? [messageId] : [];
    }),
  );
  const mergedItems: Record<string, unknown>[] = [];
  const pendingUnanchoredItems: Record<string, unknown>[] = [];
  let pendingHistoryBoundaryIndex: number | null = null;
  const consumedHistoryIndexes = new Set<number>();
  const appendHistoryRange = (endIndex: number, includeEnd: boolean) => {
    const upperBound = includeEnd ? endIndex : endIndex - 1;
    for (let index = 0; index <= upperBound; index += 1) {
      if (consumedHistoryIndexes.has(index)) continue;
      mergedItems.push(historyItems[index]);
      consumedHistoryIndexes.add(index);
    }
  };
  const appendRemainingHistory = () => {
    for (let index = 0; index < historyItems.length; index += 1) {
      if (consumedHistoryIndexes.has(index)) continue;
      mergedItems.push(historyItems[index]);
      consumedHistoryIndexes.add(index);
    }
  };
  const compactionMarkerIndex = historyItems.findIndex((historyItem) => (
    historyItem.role === "assistant"
    && typeof historyItem.content === "string"
    && historyItem.content.trim() === "[compacted context]"
  ));
  const hasCompactionMarkerBefore = (index: number): boolean => (
    compactionMarkerIndex >= 0 && compactionMarkerIndex < index
  );
  const createdAtTime = (item: Record<string, unknown>): number | null => {
    const createdAt = item.created_at;
    if (typeof createdAt !== "string") return null;
    const time = Date.parse(createdAt);
    return Number.isNaN(time) ? null : time;
  };
  const hasWorkBeforeNextMessage = (itemIndex: number): boolean => {
    for (let index = itemIndex + 1; index < timeline.items.length; index += 1) {
      const candidate = timeline.items[index];
      if (candidate.kind === "message") return false;
      return true;
    }
    return false;
  };
  const isPreCompactionStaleSnapshot = (
    item: Record<string, unknown>,
    itemIndex: number,
    historyIndex: number,
  ): boolean => {
    if (consumedHistoryIndexes.size > 0 || !isHistoricalSnapshotMessage(item)) return false;
    if (!hasCompactionMarkerBefore(historyIndex)) return false;
    const compactionMarker = historyItems[compactionMarkerIndex];
    const itemCreatedAt = createdAtTime(item);
    const compactionCreatedAt = compactionMarker ? createdAtTime(compactionMarker) : null;
    if (itemCreatedAt !== null && compactionCreatedAt !== null) {
      return itemCreatedAt < compactionCreatedAt;
    }
    return hasWorkBeforeNextMessage(itemIndex);
  };
  const matchingUniqueHistorySignatureIndex = (
    item: Record<string, unknown>,
    options?: { requireUniqueSnapshotSignature?: boolean },
  ): number => {
    const signature = messageSignature(item);
    if (!signature) return -1;
    if (historySignatureCounts.get(signature) !== 1) {
      return -1;
    }
    if (options?.requireUniqueSnapshotSignature !== false && snapshotSignatureCounts.get(signature) !== 1) {
      return -1;
    }
    return historyItems.findIndex((historyItem, candidateIndex) => (
      !consumedHistoryIndexes.has(candidateIndex)
      && messageSignature(historyItem) === signature
    ));
  };
  const preCompactionDuplicateHistoryIndex = (item: Record<string, unknown>, itemIndex: number): number => {
    if (!persistedMessageId(item)) return -1;
    const signatureIndex = matchingUniqueHistorySignatureIndex(
      item,
      { requireUniqueSnapshotSignature: false },
    );
    if (signatureIndex < 0) return -1;
    return isPreCompactionStaleSnapshot(item, itemIndex, signatureIndex) ? signatureIndex : -1;
  };
  const matchingHistoryIndex = (item: Record<string, unknown>, itemIndex: number): number => {
    const messageId = persistedMessageId(item);
    if (messageId) {
      const index = historyItems.findIndex((historyItem, candidateIndex) => (
        !consumedHistoryIndexes.has(candidateIndex)
        && persistedMessageId(historyItem) === messageId
      ));
      if (index >= 0) return index;
      if (activeTimeline && !isHistoricalSnapshotMessage(item)) return -1;
    } else if (activeTimeline && !isHistoricalSnapshotMessage(item)) {
      return -1;
    }
    const signatureIndex = matchingUniqueHistorySignatureIndex(item);
    if (messageId && signatureIndex >= 0 && isPreCompactionStaleSnapshot(item, itemIndex, signatureIndex)) {
      return -1;
    }
    return signatureIndex;
  };
  const skippedHistoryBoundaryIndex = (item: Record<string, unknown>): number => {
    const messageId = persistedMessageId(item);
    if (messageId) {
      const index = historyItems.findIndex((historyItem, candidateIndex) => (
        !consumedHistoryIndexes.has(candidateIndex)
        && persistedMessageId(historyItem) === messageId
      ));
      if (index >= 0) return index;
    }
    if (!isHistoricalSnapshotMessage(item)) return -1;
    const signature = messageSignature(item);
    if (!signature) return -1;
    return historyItems.findIndex((historyItem, candidateIndex) => (
      !consumedHistoryIndexes.has(candidateIndex)
      && messageSignature(historyItem) === signature
    ));
  };
  const rememberPendingHistoryBoundary = (item: Record<string, unknown>) => {
    if (consumedHistoryIndexes.size > 0) return;
    const boundaryIndex = skippedHistoryBoundaryIndex(item);
    if (boundaryIndex < 0) return;
    pendingHistoryBoundaryIndex = pendingHistoryBoundaryIndex === null
      ? boundaryIndex
      : Math.min(pendingHistoryBoundaryIndex, boundaryIndex);
  };
  const flushPendingAtHistoryBoundary = (): boolean => {
    if (pendingHistoryBoundaryIndex === null || pendingUnanchoredItems.length === 0) {
      return false;
    }
    appendHistoryRange(pendingHistoryBoundaryIndex, true);
    mergedItems.push(...pendingUnanchoredItems);
    pendingUnanchoredItems.length = 0;
    pendingHistoryBoundaryIndex = null;
    return true;
  };

  for (let itemIndex = 0; itemIndex < timeline.items.length; itemIndex += 1) {
    const item = timeline.items[itemIndex];
    if (consumedHistoryIndexes.size === 0 && item.kind !== "message") {
      if (mergedItems.length > 0) {
        mergedItems.push(item);
        continue;
      }
      if (flushPendingAtHistoryBoundary()) {
        mergedItems.push(item);
        continue;
      }
      pendingUnanchoredItems.push(item);
      continue;
    }
    if (item.kind !== "message") {
      mergedItems.push(item);
      continue;
    }
    const historyIndex = matchingHistoryIndex(item, itemIndex);
    if (historyIndex >= 0) {
      appendHistoryRange(historyIndex, pendingUnanchoredItems.length === 0);
      mergedItems.push(...pendingUnanchoredItems);
      pendingUnanchoredItems.length = 0;
      pendingHistoryBoundaryIndex = null;
      appendHistoryRange(historyIndex, true);
      continue;
    }
    const messageId = persistedMessageId(item);
    if (messageId && historyMessageIds.has(messageId)) {
      rememberPendingHistoryBoundary(item);
      continue;
    }
    if (messageId && isHistoricalSnapshotMessage(item)) {
      const duplicateHistoryIndex = preCompactionDuplicateHistoryIndex(item, itemIndex);
      if (duplicateHistoryIndex >= 0) {
        consumedHistoryIndexes.add(duplicateHistoryIndex);
      }
      mergedItems.push(...pendingUnanchoredItems);
      pendingUnanchoredItems.length = 0;
      pendingHistoryBoundaryIndex = null;
      mergedItems.push(item);
      continue;
    }
    if (isHistoricalSnapshotMessage(item)) {
      rememberPendingHistoryBoundary(item);
      continue;
    }
    if (activeTimeline && consumedHistoryIndexes.size === 0) {
      appendRemainingHistory();
      mergedItems.push(...pendingUnanchoredItems);
      pendingUnanchoredItems.length = 0;
      pendingHistoryBoundaryIndex = null;
      mergedItems.push(item);
      continue;
    }
    if (consumedHistoryIndexes.size === 0) {
      pendingUnanchoredItems.push(item);
      continue;
    }
    mergedItems.push(item);
  }
  flushPendingAtHistoryBoundary();
  appendRemainingHistory();
  mergedItems.push(...pendingUnanchoredItems);

  return {
    ...timeline,
    items: mergedItems,
  };
}

function timelineSessionFromDetail(detail: SessionDetailPayload): LiveSession | null {
  if (!detail.timeline) return null;
  const session = detail.session;
  return {
    live_session_id: detail.timeline.live_session_id,
    session_id: detail.timeline.session_id,
    task_id: session.task_id ?? null,
    kind: "session",
    project_dir: session.directory,
    provider_id: session.provider_id,
    profile_id: session.profile_id,
    provider: session.provider,
    model: session.model,
    reasoning_effort: detail.timeline.runtime?.reasoning_effort ?? "",
    compact_threshold: detail.timeline.runtime?.compact_threshold ?? 0,
    created_at: session.updated_at,
    status: detail.status ?? session.status ?? "idle",
    exit_code: null,
    fatal_error: detail.timeline.fatal_error,
    ended_at: null,
    last_event_seq: detail.timeline.last_event_seq,
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
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="profile-selector__trigger"
          disabled={disabled}
          aria-label={`Model profile: ${label}`}
        >
          <CpuIcon data-icon="inline-start" />
          <span className="profile-selector__name">{label}</span>
          <ChevronDownIcon data-icon="inline-end" />
        </Button>
      </DropdownMenuTrigger>

      {modelProfiles.length > 0 ? (
        <DropdownMenuContent className="profile-selector__dropdown" align="start">
          <DropdownMenuGroup>
            {modelProfiles.map((profile) => {
              const isSelected = profile.id === selectedProfileId;
              return (
                <DropdownMenuItem
                  key={profile.id}
                  className="profile-selector__option"
                  onClick={() => {
                    onChange(profile.id);
                    setIsOpen(false);
                  }}
                >
                  <span className="profile-selector__option-check">
                    {isSelected ? <CheckIcon aria-hidden="true" /> : null}
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
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      ) : null}
    </DropdownMenu>
  );
}
