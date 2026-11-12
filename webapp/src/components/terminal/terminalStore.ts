import { create } from "zustand";

export type TerminalRunRequest = { id: number; command: string };

type TerminalStore = {
  open: boolean;
  terminalId: string | null;
  pendingRun: TerminalRunRequest | null;
  setOpen: (open: boolean) => void;
  setTerminalId: (terminalId: string | null) => void;
  runCommand: (command: string) => void;
  consumeRun: (id: number) => void;
};

let nextRunId = 1;

export const SHELL_SNIPPET_LANGUAGES = new Set([
  "bash",
  "sh",
  "shell",
  "zsh",
  "console",
  "shellscript",
]);

export const useTerminalStore = create<TerminalStore>((set) => ({
  open: false,
  terminalId: null,
  pendingRun: null,
  setOpen: (open) => set({ open }),
  setTerminalId: (terminalId) => set({ terminalId }),
  runCommand: (command) =>
    set({ open: true, pendingRun: { id: nextRunId++, command } }),
  consumeRun: (id) =>
    set((state) => (state.pendingRun?.id === id ? { pendingRun: null } : state)),
}));

/** Build the text to type into the terminal for a snippet (one trailing Enter). */
export function snippetToTerminalInput(command: string): string {
  const trimmed = command.replace(/\s+$/, "");
  return `${trimmed.replace(/\r?\n/g, "\r")}\r`;
}

export function terminalSocketUrl(
  location: Pick<Location, "protocol" | "host">,
  params: { terminalId: string | null; cols: number; rows: number },
): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const search = new URLSearchParams({
    cols: String(params.cols),
    rows: String(params.rows),
  });
  if (params.terminalId) search.set("terminal_id", params.terminalId);
  return `${protocol}//${location.host}/api/terminals/ws?${search.toString()}`;
}
