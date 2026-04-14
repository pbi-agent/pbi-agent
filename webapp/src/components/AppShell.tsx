import { lazy, Suspense, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchBootstrap, fetchConfigBootstrap } from "../api";
import { useTaskEvents } from "../hooks/useTaskEvents";
import { useChatStore } from "../store";
import { LoadingSpinner } from "./shared/LoadingSpinner";
import { OnboardingModal } from "./OnboardingModal";

const ChatPage = lazy(() =>
  import("./chat/ChatPage").then((m) => ({ default: m.ChatPage })),
);
const BoardPage = lazy(() =>
  import("./board/BoardPage").then((m) => ({ default: m.BoardPage })),
);
const SettingsPage = lazy(() =>
  import("./settings/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
const DashboardPage = lazy(() =>
  import("./dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);

export function AppShell() {
  useTaskEvents();
  const location = useLocation();
  const activeChatKey = useChatStore((state) => state.activeChatKey);
  const activeChat = useChatStore((state) =>
    activeChatKey ? state.chatsByKey[activeChatKey] ?? null : null,
  );

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap"],
    queryFn: fetchBootstrap,
    staleTime: 30_000,
  });

  const configBootstrapQuery = useQuery({
    queryKey: ["config-bootstrap"],
    queryFn: fetchConfigBootstrap,
    staleTime: 30_000,
  });

  const bootstrap = bootstrapQuery.data;
  const configBootstrap = configBootstrapQuery.data;

  const requiresOnboarding = configBootstrap
    ? configBootstrap.model_profiles.length === 0
    : false;

  const [dismissedOnboardingRevision, setDismissedOnboardingRevision] = useState<string | null>(null);
  const isSettingsRoute = location.pathname === "/settings";
  const showOnboardingModal = requiresOnboarding && !(
    isSettingsRoute && dismissedOnboardingRevision === configBootstrap?.config_revision
  );

  const folderLabel = bootstrap?.workspace_root
    ? bootstrap.workspace_root.split(/[/\\]/).filter(Boolean).slice(-2).join("/")
    : null;

  const isChatRoute = location.pathname === "/chat" || location.pathname.startsWith("/chat/");

  // Derive the default runtime display from the active profile in config-bootstrap.
  // This query is kept fresh by settings-page mutations, so it always reflects the
  // current active-profile selection without requiring a full page refresh.
  const activeProfile = configBootstrap
    ? (configBootstrap.model_profiles.find((p) => p.id === configBootstrap.active_profile_id)
      ?? configBootstrap.model_profiles[0])
    : null;
  const activeRuntime = activeProfile?.resolved_runtime;

  const displayedProvider = requiresOnboarding
    ? "Not configured"
    : isChatRoute && activeChat?.liveSessionId && activeChat.runtime?.provider
      ? activeChat.runtime.provider
      : (activeRuntime?.provider ?? "...");
  const displayedModel = requiresOnboarding
    ? null
    : isChatRoute && activeChat?.liveSessionId && activeChat.runtime?.model
      ? activeChat.runtime.model
      : (activeRuntime?.model ?? "...");
  const displayedReasoningEffort = requiresOnboarding
    ? null
    : isChatRoute && activeChat?.liveSessionId && activeChat.runtime?.reasoning_effort
      ? activeChat.runtime.reasoning_effort
      : (activeRuntime?.reasoning_effort ?? null);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar__brand">
          <strong>Agent</strong> Control Room
          {folderLabel ? (
            <span className="topbar__folder" title={bootstrap?.workspace_root}>{folderLabel}</span>
          ) : null}
        </div>
        <nav className="topnav">
          <NavLink to="/chat">Chat</NavLink>
          <NavLink to="/board">Kanban</NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="runtime-meta">
          <span className="runtime-meta__pill">{displayedProvider}</span>
          {displayedModel && <span className="runtime-meta__pill">{displayedModel}</span>}
          {displayedReasoningEffort && displayedReasoningEffort !== "none" && (
            <span className="runtime-meta__pill">{displayedReasoningEffort}</span>
          )}
        </div>
      </header>

      <main className="app-main">
        <Suspense fallback={<div className="center-spinner"><LoadingSpinner size="lg" /></div>}>
          <Routes>
            <Route path="/" element={<Navigate to={requiresOnboarding ? "/settings" : "/chat"} replace />} />
            <Route
              path="/chat"
              element={
                requiresOnboarding ? <Navigate to="/settings" replace /> : (
                <ChatPage
                  workspaceRoot={bootstrap?.workspace_root}
                  supportsImageInputs={bootstrap?.supports_image_inputs ?? false}
                />
                )
              }
            />
            <Route
              path="/chat/:sessionId"
              element={
                requiresOnboarding ? <Navigate to="/settings" replace /> : (
                <ChatPage
                  workspaceRoot={bootstrap?.workspace_root}
                  supportsImageInputs={bootstrap?.supports_image_inputs ?? false}
                />
                )
              }
            />
            <Route
              path="/chat/live/:liveSessionId"
              element={
                requiresOnboarding ? <Navigate to="/settings" replace /> : (
                <ChatPage
                  workspaceRoot={bootstrap?.workspace_root}
                  supportsImageInputs={bootstrap?.supports_image_inputs ?? false}
                />
                )
              }
            />
            <Route path="/board" element={requiresOnboarding ? <Navigate to="/settings" replace /> : <BoardPage />} />
            <Route path="/dashboard" element={requiresOnboarding ? <Navigate to="/settings" replace /> : <DashboardPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </Suspense>
      </main>

      {showOnboardingModal && (
        <OnboardingModal
          isOnSettingsPage={isSettingsRoute}
          onDismissOnSettings={() => {
            setDismissedOnboardingRevision(configBootstrap?.config_revision ?? null);
          }}
        />
      )}
    </div>
  );
}
