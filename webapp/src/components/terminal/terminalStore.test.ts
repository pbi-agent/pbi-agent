import { beforeEach, describe, expect, it } from "vitest";
import {
  snippetToTerminalInput,
  terminalSocketUrl,
  useTerminalStore,
} from "./terminalStore";

describe("terminalStore", () => {
  beforeEach(() => {
    useTerminalStore.setState({ open: false, terminalId: null, pendingRun: null });
  });

  it("opens the terminal and queues a snippet run", () => {
    useTerminalStore.getState().runCommand("echo hi");
    const state = useTerminalStore.getState();
    expect(state.open).toBe(true);
    expect(state.pendingRun?.command).toBe("echo hi");
    state.consumeRun(state.pendingRun!.id);
    expect(useTerminalStore.getState().pendingRun).toBeNull();
  });

  it("converts snippets to terminal keystrokes", () => {
    expect(snippetToTerminalInput("a\nb\n\n")).toBe("a\rb\r");
  });

  it("builds websocket urls", () => {
    expect(
      terminalSocketUrl({ protocol: "https:", host: "h:1" }, { terminalId: "t1", cols: 80, rows: 24 }),
    ).toBe("wss://h:1/api/terminals/ws?cols=80&rows=24&terminal_id=t1");
    expect(
      terminalSocketUrl({ protocol: "http:", host: "h" }, { terminalId: null, cols: 1, rows: 2 }),
    ).toBe("ws://h/api/terminals/ws?cols=1&rows=2");
  });
});
