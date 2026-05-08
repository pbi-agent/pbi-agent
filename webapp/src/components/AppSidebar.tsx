import type React from "react";
import { BarChart3Icon, KanbanSquareIcon, MessageSquareTextIcon, SettingsIcon } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useSettingsDialog } from "../hooks/useSettingsDialog";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

const appNavItems = [
  { to: "/sessions", label: "Sessions", icon: MessageSquareTextIcon },
  { to: "/board", label: "Kanban", icon: KanbanSquareIcon },
  { to: "/dashboard", label: "Dashboard", icon: BarChart3Icon },
];

export function AppSidebarSettings({ collapsed = false }: { collapsed?: boolean }) {
  const { openSettings } = useSettingsDialog();

  return (
    <Button
      type="button"
      variant="ghost"
      size={collapsed ? "icon-sm" : "sm"}
      className="app-sidebar-nav__item app-sidebar-nav__settings"
      onClick={openSettings}
      title={collapsed ? "Settings" : undefined}
      aria-label={collapsed ? "Settings" : undefined}
    >
      <SettingsIcon data-icon="inline-start" />
      {!collapsed && <span>Settings</span>}
    </Button>
  );
}

export function AppSidebarNav({
  collapsed = false,
  showSettings = true,
}: {
  collapsed?: boolean;
  showSettings?: boolean;
}) {
  return (
    <nav
      className={cn("app-sidebar-nav", collapsed && "app-sidebar-nav--collapsed")}
      aria-label="Primary navigation"
    >
      <div className="app-sidebar-nav__items">
        {appNavItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "app-sidebar-nav__item",
                isActive && "app-sidebar-nav__item--active",
              )
            }
            title={collapsed ? label : undefined}
            aria-label={collapsed ? label : undefined}
          >
            <Icon />
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </div>
      {showSettings ? <AppSidebarSettings collapsed={collapsed} /> : null}
    </nav>
  );
}

export function AppSidebar() {
  return (
    <aside className="app-sidebar" aria-label="Application sidebar">
      <AppSidebarNav />
    </aside>
  );
}

export function AppSidebarLayout({ children }: { children: React.ReactNode }) {
  return (
    <section className="app-sidebar-layout">
      <AppSidebar />
      <div className="app-sidebar-layout__content">{children}</div>
    </section>
  );
}
