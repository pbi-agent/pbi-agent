import { useEffect } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type SidebarStore = {
  isOpen: boolean;
  toggle: () => void;
  open: () => void;
  close: () => void;
  setOpen: (next: boolean) => void;
};

export const useSidebarStore = create<SidebarStore>()(
  persist(
    (set) => ({
      isOpen: true,
      toggle: () => set((state) => ({ isOpen: !state.isOpen })),
      open: () => set({ isOpen: true }),
      close: () => set({ isOpen: false }),
      setOpen: (next) => set({ isOpen: next }),
    }),
    {
      name: "pbi-agent.sidebar",
      version: 1,
      partialize: (state) => ({ isOpen: state.isOpen }),
    },
  ),
);

/**
 * Listen for Cmd/Ctrl+B globally and toggle the sidebar.
 *
 * The shortcut is intentionally routed through a single hook installed at
 * the AppShell level so every page (sessions, board, dashboard, ...) gets
 * the same behavior without duplicating listeners.
 */
export function useSidebarShortcut() {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.altKey || event.shiftKey) return;
      if (!(event.metaKey || event.ctrlKey)) return;
      if (event.key.toLowerCase() !== "b") return;
      event.preventDefault();
      useSidebarStore.getState().toggle();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
