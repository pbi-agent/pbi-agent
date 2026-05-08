import type { ComponentType, ReactNode, SVGProps } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3Icon,
  KanbanSquareIcon,
  MessageSquareTextIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  SettingsIcon,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { fetchBootstrap } from "../api";
import { useSettingsDialog } from "../hooks/useSettingsDialog";
import { useSidebarStore } from "../hooks/useSidebar";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { cn } from "../lib/utils";

type IconType = ComponentType<SVGProps<SVGSVGElement>>;

type NavItem = {
  to: string;
  label: string;
  icon: IconType;
};

const appNavItems: NavItem[] = [
  { to: "/sessions", label: "Sessions", icon: MessageSquareTextIcon },
  { to: "/board", label: "Kanban", icon: KanbanSquareIcon },
  { to: "/dashboard", label: "Dashboard", icon: BarChart3Icon },
];

const TOGGLE_SHORTCUT_HINT =
  typeof navigator !== "undefined" && /Mac|iP(hone|ad|od)/.test(navigator.platform)
    ? "⌘B"
    : "Ctrl+B";

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
            {isOpen ? <PanelLeftCloseIcon /> : <PanelLeftOpenIcon />}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right" className="app-sidebar__toggle-tooltip">
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

  return (
    <div className="app-sidebar__workspace">
      <Badge
        variant="outline"
        className="app-sidebar__workspace-badge"
        title={workspaceDisplayPath ?? undefined}
      >
        {workspaceBadgeLabel}
      </Badge>
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
  const link = (
    <NavLink
      to={item.to}
      className={({ isActive }) =>
        cn(
          "app-sidebar__nav-item",
          collapsed && "app-sidebar__nav-item--collapsed",
          isActive && "app-sidebar__nav-item--active",
        )
      }
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
      <SettingsIcon aria-hidden="true" />
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
