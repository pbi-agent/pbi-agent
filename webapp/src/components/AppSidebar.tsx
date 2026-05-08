import type { ComponentType, ReactNode, SVGProps } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, useLocation } from "react-router-dom";
import { fetchBootstrap } from "../api";
import { useSettingsDialog } from "../hooks/useSettingsDialog";
import { useSidebarStore } from "../hooks/useSidebar";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { cn } from "../lib/utils";

type IconType = ComponentType<SVGProps<SVGSVGElement>>;

type SidebarIconBaseProps = SVGProps<SVGSVGElement> & {
  children: ReactNode;
};

function SidebarIconBase({ children, className, ...props }: SidebarIconBaseProps) {
  return (
    <svg
      width="24"
      height="24"
      {...props}
      className={cn("app-sidebar__icon", className)}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

function SidebarIconTile() {
  return <rect x="3.25" y="3.25" width="13.5" height="13.5" rx="2.75" />;
}

function SidebarSessionsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <SidebarIconBase {...props}>
      <SidebarIconTile />
      <path d="M6.4 7.25h7.2" />
      <path d="M6.4 10h6" />
      <path d="M6.4 12.75h4.1" />
    </SidebarIconBase>
  );
}

function SidebarKanbanIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <SidebarIconBase {...props}>
      <SidebarIconTile />
      <path d="M6.6 6.75v6.5" />
      <path d="M10 6.75v6.5" />
      <path d="M13.4 6.75v6.5" />
      <path d="M5.9 8.85h8.2" />
    </SidebarIconBase>
  );
}

function SidebarDashboardIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <SidebarIconBase {...props}>
      <SidebarIconTile />
      <path d="M6.45 13.25v-3" />
      <path d="M10 13.25v-6.5" />
      <path d="M13.55 13.25v-4.6" />
      <path d="M5.9 13.25h8.2" />
    </SidebarIconBase>
  );
}

function SidebarSettingsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <SidebarIconBase {...props}>
      <SidebarIconTile />
      <path d="M6.2 7.15h7.6" />
      <path d="M8.35 6.25v1.8" />
      <path d="M6.2 10h7.6" />
      <path d="M11.65 9.1v1.8" />
      <path d="M6.2 12.85h7.6" />
      <path d="M9.55 11.95v1.8" />
    </SidebarIconBase>
  );
}

function SidebarCollapseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <SidebarIconBase {...props}>
      <SidebarIconTile />
      <path d="M7.45 4.05v11.9" />
      <path d="M13 7.4 10.4 10 13 12.6" />
    </SidebarIconBase>
  );
}

function SidebarExpandIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <SidebarIconBase {...props}>
      <SidebarIconTile />
      <path d="M7.45 4.05v11.9" />
      <path d="M10.4 7.4 13 10l-2.6 2.6" />
    </SidebarIconBase>
  );
}

type NavItem = {
  to: string;
  label: string;
  icon: IconType;
};

const appNavItems: NavItem[] = [
  { to: "/sessions", label: "Sessions", icon: SidebarSessionsIcon },
  { to: "/board", label: "Kanban", icon: SidebarKanbanIcon },
  { to: "/dashboard", label: "Dashboard", icon: SidebarDashboardIcon },
];

const TOGGLE_SHORTCUT_HINT =
  typeof navigator !== "undefined" && /Mac|iP(hone|ad|od)/.test(navigator.platform)
    ? "⌘B"
    : "Ctrl+B";

function isNavItemActive(pathname: string, itemPath: string) {
  if (itemPath === "/sessions") {
    return pathname === itemPath || pathname.startsWith(`${itemPath}/`);
  }
  return pathname === itemPath;
}

export type AppSidebarLayoutProps = {
  children: ReactNode;
  contextPanel?: ReactNode;
};

/**
 * Top-level shell layout: persistent collapsible sidebar + main content area.
 * Used by every primary route (sessions, board, dashboard) so navigation and
 * collapse state stay consistent.
 */
export function AppSidebarLayout({ children, contextPanel }: AppSidebarLayoutProps) {
  const isOpen = useSidebarStore((state) => state.isOpen);
  const close = useSidebarStore((state) => state.close);

  function handleMainClick() {
    if (isOpen) close();
  }

  return (
    <div
      className={cn(
        "app-shell-layout",
        isOpen ? "app-shell-layout--open" : "app-shell-layout--collapsed",
      )}
      data-sidebar-state={isOpen ? "open" : "collapsed"}
    >
      <AppSidebar contextPanel={contextPanel} />
      <div className="app-shell-layout__main" onClick={handleMainClick}>
        {children}
      </div>
    </div>
  );
}

function AppSidebar({ contextPanel }: { contextPanel?: ReactNode }) {
  const isOpen = useSidebarStore((state) => state.isOpen);
  return (
    <aside
      id="app-sidebar"
      className={cn("app-sidebar", !isOpen && "app-sidebar--collapsed")}
      aria-label="Application sidebar"
    >
      <AppSidebarHead />
      <AppSidebarWorkspace />
      <AppSidebarNav collapsed={!isOpen} />
      {isOpen ? (
        <div className="app-sidebar__context">
          {contextPanel ?? <div className="app-sidebar__context-spacer" aria-hidden="true" />}
        </div>
      ) : (
        <div className="app-sidebar__context-spacer" aria-hidden="true" />
      )}
      <AppSidebarFooter collapsed={!isOpen} />
    </aside>
  );
}

function AppSidebarHead() {
  const isOpen = useSidebarStore((state) => state.isOpen);
  const toggle = useSidebarStore((state) => state.toggle);
  const toggleLabel = isOpen ? "Collapse sidebar" : "Expand sidebar";
  return (
    <div className="app-sidebar__head">
      {isOpen ? (
        <div className="app-sidebar__brand" aria-hidden="true">
          <span className="app-sidebar__brand-mark">PA</span>
          <span className="app-sidebar__brand-name">
            <strong>pbi</strong>-agent
          </span>
        </div>
      ) : null}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="app-sidebar__toggle"
            onClick={toggle}
            aria-label={toggleLabel}
            aria-expanded={isOpen}
            aria-controls="app-sidebar"
          >
            {isOpen ? (
              <SidebarCollapseIcon aria-hidden="true" />
            ) : (
              <SidebarExpandIcon aria-hidden="true" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right">
          <span>{toggleLabel}</span>
          <kbd className="app-sidebar__toggle-shortcut">{TOGGLE_SHORTCUT_HINT}</kbd>
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

function AppSidebarWorkspace() {
  const isOpen = useSidebarStore((state) => state.isOpen);
  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap"],
    queryFn: fetchBootstrap,
    staleTime: 30_000,
  });

  if (!isOpen) return null;

  const bootstrap = bootstrapQuery.data;
  const workspaceDisplayPath = bootstrap?.workspace_display_path;
  const folderLabel = workspaceDisplayPath
    ? workspaceDisplayPath.split(/[/\\]/).filter(Boolean).slice(-2).join("/")
    : null;
  const workspaceBadgeLabel = bootstrap?.is_sandbox && folderLabel
    ? `Sandbox · ${folderLabel}`
    : folderLabel;

  if (!workspaceBadgeLabel) return null;

  const workspaceBadge = (
    <Badge
      variant="outline"
      className="app-sidebar__workspace-badge"
    >
      {workspaceBadgeLabel}
    </Badge>
  );

  return (
    <div className="app-sidebar__workspace">
      {workspaceDisplayPath ? (
        <Tooltip>
          <TooltipTrigger asChild>{workspaceBadge}</TooltipTrigger>
          <TooltipContent side="right">{workspaceDisplayPath}</TooltipContent>
        </Tooltip>
      ) : workspaceBadge}
    </div>
  );
}

function AppSidebarNav({ collapsed }: { collapsed: boolean }) {
  return (
    <nav
      className={cn("app-sidebar__nav", collapsed && "app-sidebar__nav--collapsed")}
      aria-label="Primary navigation"
    >
      {appNavItems.map((item) => (
        <SidebarNavLink key={item.to} item={item} collapsed={collapsed} />
      ))}
    </nav>
  );
}

function SidebarNavLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const Icon = item.icon;
  const { pathname } = useLocation();
  const isActive = isNavItemActive(pathname, item.to);
  const link = (
    <NavLink
      to={item.to}
      className={cn(
        "app-sidebar__nav-item",
        collapsed && "app-sidebar__nav-item--collapsed",
        isActive && "app-sidebar__nav-item--active",
      )}
      aria-label={collapsed ? item.label : undefined}
    >
      <Icon aria-hidden="true" />
      {!collapsed && <span>{item.label}</span>}
    </NavLink>
  );

  if (!collapsed) return link;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{item.label}</TooltipContent>
    </Tooltip>
  );
}

function AppSidebarFooter({ collapsed }: { collapsed: boolean }) {
  return (
    <div
      className={cn(
        "app-sidebar__footer",
        collapsed && "app-sidebar__footer--collapsed",
      )}
    >
      <SettingsButton collapsed={collapsed} />
    </div>
  );
}

function SettingsButton({ collapsed }: { collapsed: boolean }) {
  const { openSettings } = useSettingsDialog();
  const button = (
    <button
      type="button"
      className={cn(
        "app-sidebar__nav-item app-sidebar__footer-button",
        collapsed && "app-sidebar__nav-item--collapsed",
      )}
      onClick={openSettings}
      aria-label="Settings"
    >
      <SidebarSettingsIcon aria-hidden="true" />
      {!collapsed && <span>Settings</span>}
    </button>
  );

  if (!collapsed) return button;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right">Settings</TooltipContent>
    </Tooltip>
  );
}
