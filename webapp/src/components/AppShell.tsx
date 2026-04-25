import { lazy, Suspense, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3Icon,
  CheckIcon,
  KanbanSquareIcon,
  MessageSquareTextIcon,
  MoonStarIcon,
  PaletteIcon,
  SettingsIcon,
  SunIcon,
} from "lucide-react";
import { fetchBootstrap, fetchConfigBootstrap } from "../api";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
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

const themeIcons: Record<AppTheme, typeof SunIcon> = {
  light: SunIcon,
  dark: MoonStarIcon,
  prism: PaletteIcon,
};

export function AppShell() {
  useTaskEvents();
  const { theme, setTheme } = useTheme();
  const location = useLocation();

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

  const ThemeIcon = themeIcons[theme];

  return (
    <div className="app-shell bg-background text-foreground">
      <header className="header">
        <div className="header__left">
          {folderLabel && (
            <Badge variant="outline" className="header__workspace overflow-visible" title={bootstrap?.workspace_root}>
              {folderLabel}
            </Badge>
          )}
        </div>

        {/* Navigation */}
        <nav className="header__nav" aria-label="Primary navigation">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className="header__nav-link">
              <Icon />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="header__right">
          {/* Theme dropdown */}
          <DropdownMenu>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon-sm" aria-label="Change theme">
                    <ThemeIcon />
                  </Button>
                </DropdownMenuTrigger>
              </TooltipTrigger>
              <TooltipContent side="bottom">Theme</TooltipContent>
            </Tooltip>
            <DropdownMenuContent align="end" className="min-w-36">
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
