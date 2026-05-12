import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchBootstrap, fetchConfigBootstrap } from "../api";
import { useSettingsDialog } from "../hooks/useSettingsDialog";
import { useSidebarShortcut } from "../hooks/useSidebar";
import { useTaskEvents } from "../hooks/useTaskEvents";
import { AskUserNotificationEffects } from "./notifications/AskUserNotificationEffects";
import { SessionEndedNotificationEffects } from "./notifications/SessionEndedNotificationEffects";
import { LoadingSpinner } from "./shared/LoadingSpinner";
import { OnboardingModal } from "./OnboardingModal";
import { AppSidebarLayout } from "./AppSidebar";

const SessionPage = lazy(() =>
  import("./session/SessionPage").then((m) => ({ default: m.SessionPage })),
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
  // Global Cmd/Ctrl+B sidebar toggle, available on every route.
  useSidebarShortcut();

  const liveSessionEvents = useTaskEvents();

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

  const [dismissedOnboardingOnSettings, setDismissedOnboardingOnSettings] = useState(false);
  const { open: settingsOpen, openSettings } = useSettingsDialog();

  // Auto-open settings when onboarding is required
  useEffect(() => {
    if (requiresOnboarding && !settingsOpen) {
      openSettings();
    }
  }, [requiresOnboarding]); // eslint-disable-line react-hooks/exhaustive-deps

  const showOnboardingModal = requiresOnboarding && !(
    settingsOpen && dismissedOnboardingOnSettings
  );

  return (
    <div className="app-shell bg-background text-foreground">
      <AskUserNotificationEffects />
      <SessionEndedNotificationEffects
        liveSessionEvents={liveSessionEvents}
        liveSessions={bootstrap?.live_sessions ?? []}
        tasks={bootstrap?.tasks ?? []}
      />

      <Suspense fallback={<div className="center-spinner"><LoadingSpinner size="lg" /></div>}>
        <Routes>
          <Route path="/" element={<Navigate to="/sessions" replace />} />
          <Route
            path="/sessions"
            element={
              <SessionPage
                workspaceRoot={bootstrap?.workspace_root}
                supportsImageInputs={bootstrap?.supports_image_inputs ?? false}
              />
            }
          />
          <Route
            path="/sessions/:sessionId/sub-agents/:subAgentId"
            element={
              <SessionPage
                workspaceRoot={bootstrap?.workspace_root}
                supportsImageInputs={bootstrap?.supports_image_inputs ?? false}
              />
            }
          />
          <Route
            path="/sessions/:sessionId"
            element={
              <SessionPage
                workspaceRoot={bootstrap?.workspace_root}
                supportsImageInputs={bootstrap?.supports_image_inputs ?? false}
              />
            }
          />
          <Route
            path="/board"
            element={(
              <AppSidebarLayout>
                <BoardPage />
              </AppSidebarLayout>
            )}
          />
          <Route
            path="/dashboard"
            element={(
              <AppSidebarLayout>
                <DashboardPage />
              </AppSidebarLayout>
            )}
          />
          <Route path="/settings" element={<Navigate to="/sessions" replace />} />
        </Routes>
      </Suspense>

      <Suspense>
        <SettingsPage />
      </Suspense>

      {showOnboardingModal && (
        <OnboardingModal
          openSettings={openSettings}
          isOnSettingsPage={settingsOpen}
          onDismissOnSettings={() => {
            setDismissedOnboardingOnSettings(true);
          }}
        />
      )}
    </div>
  );
}
