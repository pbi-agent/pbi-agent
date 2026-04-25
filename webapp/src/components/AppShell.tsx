import { lazy, Suspense, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BarChart3Icon, KanbanSquareIcon, MessageSquareTextIcon, SettingsIcon } from "lucide-react";
import { fetchBootstrap, fetchConfigBootstrap } from "../api";
import { useTaskEvents } from "../hooks/useTaskEvents";
import { useSessionStore } from "../store";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { LoadingSpinner } from "./shared/LoadingSpinner";
import { OnboardingModal } from "./OnboardingModal";
import { themeOptions, useTheme, type AppTheme } from "./ThemeProvider";

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

const navItems = [
  { to: "/sessions", label: "Sessions", icon: MessageSquareTextIcon },
  { to: "/board", label: "Kanban", icon: KanbanSquareIcon },
  { to: "/dashboard", label: "Dashboard", icon: BarChart3Icon },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export function AppShell() {
  useTaskEvents();
  const { theme, setTheme } = useTheme();
  const location = useLocation();
  const activeSessionKey = useSessionStore((state) => state.activeSessionKey);
  const activeSession = useSessionStore((state) =>
    activeSessionKey ? state.sessionsByKey[activeSessionKey] ?? null : null,
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

  const [dismissedOnboardingOnSettings, setDismissedOnboardingOnSettings] = useState(false);
  const isSettingsRoute = location.pathname === "/settings";

  const showOnboardingModal = requiresOnboarding && !(
    isSettingsRoute && dismissedOnboardingOnSettings
  );

  const folderLabel = bootstrap?.workspace_root
    ? bootstrap.workspace_root.split(/[/\\]/).filter(Boolean).slice(-2).join("/")
    : null;

  const isSessionRoute = location.pathname === "/sessions" || location.pathname.startsWith("/sessions/");

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
    : isSessionRoute && activeSession?.liveSessionId && activeSession.runtime?.provider
      ? activeSession.runtime.provider
      : (activeRuntime?.provider ?? "...");
  const displayedModel = requiresOnboarding
    ? null
    : isSessionRoute && activeSession?.liveSessionId && activeSession.runtime?.model
      ? activeSession.runtime.model
      : (activeRuntime?.model ?? "...");
  const displayedReasoningEffort = requiresOnboarding
    ? null
    : isSessionRoute && activeSession?.liveSessionId && activeSession.runtime?.reasoning_effort
      ? activeSession.runtime.reasoning_effort
      : (activeRuntime?.reasoning_effort ?? null);

  return (
    <div className="app-shell bg-background text-foreground">
      <header className="topbar border-b border-border bg-sidebar/90 backdrop-blur-xl">
        <div className="topbar__brand">
          <span className="topbar__brand-mark">P</span>
          <span className="topbar__brand-copy">
            <strong>Prism</strong>
            <span>Agent</span>
          </span>
          {folderLabel ? (
            <Badge variant="outline" className="topbar__folder" title={bootstrap?.workspace_root}>
              {folderLabel}
            </Badge>
          ) : null}
        </div>

        <nav className="topnav" aria-label="Primary navigation">
          {navItems.map(({ to, label, icon: Icon }) => (
            <Button key={to} variant="ghost" size="sm" asChild>
              <NavLink to={to}>
                <Icon data-icon="inline-start" />
                {label}
              </NavLink>
            </Button>
          ))}
        </nav>

        <div className="runtime-meta">
          <Badge variant={requiresOnboarding ? "destructive" : "secondary"} className="runtime-meta__pill">
            {displayedProvider}
          </Badge>
          {displayedModel && <Badge variant="outline" className="runtime-meta__pill">{displayedModel}</Badge>}
          {displayedReasoningEffort && displayedReasoningEffort !== "none" && (
            <Badge variant="outline" className="runtime-meta__pill">{displayedReasoningEffort}</Badge>
          )}
        </div>

        <ToggleGroup
          type="single"
          value={theme}
          onValueChange={(value) => {
            if (value) setTheme(value as AppTheme);
          }}
          className="theme-switcher"
          aria-label="Theme"
          spacing={1}
          size="sm"
          variant="outline"
        >
          {themeOptions.map((option) => (
            <ToggleGroupItem key={option.value} value={option.value} aria-label={`${option.label} theme`}>
              {option.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </header>

      <main className="app-main">
        <Suspense fallback={<div className="center-spinner"><LoadingSpinner size="lg" /></div>}>
          <Routes>
            <Route path="/" element={<Navigate to={requiresOnboarding ? "/settings" : "/sessions"} replace />} />
            <Route
              path="/sessions"
              element={
                requiresOnboarding ? <Navigate to="/settings" replace /> : (
                <SessionPage
                  workspaceRoot={bootstrap?.workspace_root}
                  supportsImageInputs={bootstrap?.supports_image_inputs ?? false}
                />
                )
              }
            />
            <Route
              path="/sessions/:sessionId"
              element={
                requiresOnboarding ? <Navigate to="/settings" replace /> : (
                <SessionPage
                  workspaceRoot={bootstrap?.workspace_root}
                  supportsImageInputs={bootstrap?.supports_image_inputs ?? false}
                />
                )
              }
            />
            <Route
              path="/sessions/live/:liveSessionId"
              element={
                requiresOnboarding ? <Navigate to="/settings" replace /> : (
                <SessionPage
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
            setDismissedOnboardingOnSettings(true);
          }}
        />
      )}
    </div>
  );
}
