import { create } from "zustand";

type SettingsDialogStore = {
  open: boolean;
  openSettings: () => void;
  closeSettings: () => void;
};

export const useSettingsDialog = create<SettingsDialogStore>((set) => ({
  open: false,
  openSettings: () => set({ open: true }),
  closeSettings: () => set({ open: false }),
}));
