import type { ComponentType, ReactNode, SVGProps } from "react";
import {
  ChartNoAxesCombinedIcon,
  MessageSquareDotIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  SettingsIcon,
  SquareKanbanIcon,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { useLastOpenedSessionPath } from "../hooks/useLastOpenedSession";
import { useSettingsDialog } from "../hooks/useSettingsDialog";
import { useSidebarStore } from "../hooks/useSidebar";
import { AppSessionsContextPanel } from "./AppSessionsContextPanel";
import { WorkspaceBadge } from "./WorkspaceBadge";
import { Button } from "./ui/button";
import { Kbd } from "./ui/kbd";
import { Separator } from "./ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { cn } from "../lib/utils";

function navItemClassName(collapsed: boolean, isActive: boolean) {
  return cn(
    "group/nav flex items-center gap-2 rounded-md text-sm font-medium text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50",
    collapsed ? "size-10 shrink-0 justify-center" : "min-h-9 w-full justify-start px-3 py-2",
    isActive && "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary",
  );
}

type IconType = ComponentType<SVGProps<SVGSVGElement>>;

function sidebarIconClassName(className?: string) {
  return cn("size-5 shrink-0 opacity-80 transition-opacity group-hover/nav:opacity-100 group-data-[active=true]/nav:opacity-100", className);
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
      className="flex min-h-0 flex-1 overflow-hidden"
      data-sidebar-state={isOpen ? "open" : "collapsed"}
    >
      <AppSidebar contextPanel={contextPanel} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden" onClick={handleMainClick}>
        {children}
      </div>
    </div>
  );
}

function AppSidebar({ contextPanel }: { contextPanel?: ReactNode }) {
  const isOpen = useSidebarStore((state) => state.isOpen);
  const resolvedContext = contextPanel ?? <AppSessionsContextPanel />;
  return (
    <aside
      id="app-sidebar"
      data-state={isOpen ? "open" : "collapsed"}
      className={cn(
        "flex h-full min-h-0 shrink-0 flex-col overflow-hidden border-r border-border bg-sidebar text-sidebar-foreground transition-all",
        isOpen ? "w-70 max-md:w-4/5" : "w-12",
      )}
      aria-label="Application sidebar"
    >
      <AppSidebarHead />
      <AppSidebarNav collapsed={!isOpen} />
      {isOpen ? (
        <>
          <Separator className="mx-3 w-auto shrink-0" />
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{resolvedContext}</div>
        </>
      ) : (
        <div className="flex-1" aria-hidden="true" />
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
    <div
      data-sidebar-part="head"
      className={cn(
        "flex h-12 shrink-0 items-center gap-2 border-b border-border",
        isOpen ? "px-3" : "justify-center",
      )}
    >
      {isOpen ? (
        <>
          <div
            data-sidebar-part="brand"
            className="flex w-10 shrink-0 items-center"
            aria-hidden="true"
          >
            <img
              data-sidebar-part="brand-logo"
              className="block size-7 shrink-0 rounded-lg object-cover"
              src="/logo.jpg"
              alt=""
              draggable={false}
            />
          </div>
          <div
            data-sidebar-part="workspace-slot"
            className="flex min-w-0 flex-1 items-center justify-center overflow-hidden"
          >
            <WorkspaceBadge tooltipSide="right" />
          </div>
        </>
      ) : null}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="group/nav size-10 shrink-0"
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
          <Kbd>{TOGGLE_SHORTCUT_HINT}</Kbd>
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

function AppSidebarNav({ collapsed }: { collapsed: boolean }) {
  const lastOpenedSessionPath = useLastOpenedSessionPath();
  return (
    <nav
      className={cn(
        "flex shrink-0 flex-col gap-px",
        collapsed ? "items-center py-2" : "px-3 pt-3 pb-2",
      )}
      aria-label="Primary navigation"
    >
      {appNavItems.map((item) => (
        <SidebarNavLink
          key={item.to}
          item={item}
          collapsed={collapsed}
          targetPath={item.to === "/sessions" ? lastOpenedSessionPath : item.to}
        />
      ))}
    </nav>
  );
}

function SidebarNavLink({
  item,
  collapsed,
  targetPath,
}: {
  item: NavItem;
  collapsed: boolean;
  targetPath: string;
}) {
  const Icon = item.icon;
  const { pathname } = useLocation();
  const isActive = isNavItemActive(pathname, item.to);
  const link = (
    <NavLink
      to={targetPath}
      data-collapsed={collapsed || undefined}
      data-active={isActive || undefined}
      className={navItemClassName(collapsed, isActive)}
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
        "flex shrink-0 items-center gap-2",
        collapsed ? "flex-col py-3" : "p-3",
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
      data-collapsed={collapsed || undefined}
      className={navItemClassName(collapsed, false)}
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
