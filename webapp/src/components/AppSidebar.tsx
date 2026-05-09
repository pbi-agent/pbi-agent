import type { ComponentType, ReactNode, SVGProps } from "react";
import {
  ChartNoAxesCombinedIcon,
  MessageSquareDotIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  SettingsIcon,
  SquareKanbanIcon,
} from "lucide-react";
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

function sidebarIconClassName(className?: string) {
  return cn("app-sidebar__icon", className);
}

function SidebarSessionsIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return <MessageSquareDotIcon {...props} className={sidebarIconClassName(className)} />;
}

function SidebarKanbanIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return <SquareKanbanIcon {...props} className={sidebarIconClassName(className)} />;
}

function SidebarDashboardIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return <ChartNoAxesCombinedIcon {...props} className={sidebarIconClassName(className)} />;
}

function SidebarSettingsIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return <SettingsIcon {...props} className={sidebarIconClassName(className)} />;
}

function SidebarCollapseIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return <PanelLeftCloseIcon {...props} className={sidebarIconClassName(className)} />;
}

function SidebarExpandIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return <PanelLeftOpenIcon {...props} className={sidebarIconClassName(className)} />;
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
        <>
          <div className="app-sidebar__brand" aria-hidden="true">
            <img
              className="app-sidebar__brand-logo"
              src="/logo.jpg"
              alt=""
              draggable={false}
            />
          </div>
          <div className="app-sidebar__workspace-slot">
            <AppSidebarWorkspaceBadge />
          </div>
        </>
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

function AppSidebarWorkspaceBadge() {
  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap"],
    queryFn: fetchBootstrap,
    staleTime: 30_000,
  });

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
      <span className="app-sidebar__workspace-badge-text">{workspaceBadgeLabel}</span>
    </Badge>
  );

  return (
    workspaceDisplayPath ? (
      <Tooltip>
        <TooltipTrigger asChild>{workspaceBadge}</TooltipTrigger>
        <TooltipContent side="right">{workspaceDisplayPath}</TooltipContent>
      </Tooltip>
    ) : workspaceBadge
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
