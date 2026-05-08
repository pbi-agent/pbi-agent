import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  CheckIcon,
  MoonStarIcon,
  PaletteIcon,
  SunIcon,
} from "lucide-react";
import { fetchBootstrap, fetchConfigBootstrap } from "../api";
import { useSettingsDialog } from "../hooks/useSettingsDialog";
import { useTaskEvents } from "../hooks/useTaskEvents";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { AskUserNotificationEffects } from "./notifications/AskUserNotificationEffects";
import { SessionEndedNotificationEffects } from "./notifications/SessionEndedNotificationEffects";
import { LoadingSpinner } from "./shared/LoadingSpinner";
import { OnboardingModal } from "./OnboardingModal";
import { themeOptions, useTheme, type AppTheme } from "./ThemeProvider";
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

const themeIcons: Record<AppTheme, typeof SunIcon> = {
  light: SunIcon,
  dark: MoonStarIcon,
  prism: PaletteIcon,
};

export function AppShell() {
  const liveSessionEvents = useTaskEvents();
  const { theme, setTheme } = useTheme();

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

  const workspaceDisplayPath = bootstrap?.workspace_display_path;
  const folderLabel = workspaceDisplayPath
    ? workspaceDisplayPath.split(/[/\\]/).filter(Boolean).slice(-2).join("/")
    : null;
  const workspaceBadgeLabel = bootstrap?.is_sandbox && folderLabel
    ? `Sandbox · ${folderLabel}`
    : folderLabel;

  const ThemeIcon = themeIcons[theme];

  return (
    <div className="app-shell bg-background text-foreground">
      <AskUserNotificationEffects />
      <SessionEndedNotificationEffects
        liveSessionEvents={liveSessionEvents}
        liveSessions={bootstrap?.live_sessions ?? []}
        tasks={bootstrap?.tasks ?? []}
      />
      <header className="header">
        <div className="header__left">
          {workspaceBadgeLabel && (
            <Badge variant="outline" className="header__workspace overflow-visible" title={workspaceDisplayPath}>
              {workspaceBadgeLabel}
            </Badge>
          )}
        </div>

        <div className="header__right">
          {/* Theme dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                title="Change theme"
                aria-label="Change theme"
              >
                <ThemeIcon />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuGroup>
                {themeOptions.map((option) => {
                  const OptionIcon = themeIcons[option.value];
                  return (
                    <DropdownMenuItem
                      key={option.value}
                      onSelect={() => setTheme(option.value)}
                    >
                      <OptionIcon />
                      {option.label}
                      {theme === option.value && <CheckIcon className="ml-auto text-primary" />}
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <main className="app-main">
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
      </main>

      <Suspense>
        <SettingsPage />
      </Suspense>

      {showOnboardingModal && (
        <OnboardingModal
          isOnSettingsPage={settingsOpen}
          onDismissOnSettings={() => {
            setDismissedOnboardingOnSettings(true);
          }}
        />
      )}
    </div>
  );
}
