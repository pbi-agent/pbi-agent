import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { RotateCcwIcon, XIcon } from "lucide-react";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  snippetToTerminalInput,
  terminalSocketUrl,
  useTerminalStore,
} from "./terminalStore";

type Status = "connecting" | "connected" | "disconnected" | "exited";

const STATUS_LABEL: Record<Status, string> = {
  connecting: "Connecting",
  connected: "Connected",
  disconnected: "Disconnected",
  exited: "Exited",
};

const STATUS_VARIANT = {
  connecting: "warning",
  connected: "running",
  disconnected: "failed",
  exited: "warning",
} as const;

function cssVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

type Props = { onClose?: () => void };

export function TerminalPanel({ onClose }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<Status>("connecting");
  const [generation, setGeneration] = useState(0);
  const pendingRun = useTerminalStore((state) => state.pendingRun);
  const consumeRun = useTerminalStore((state) => state.consumeRun);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const term = new Terminal({
      cursorBlink: true,
      convertEol: false,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
      fontSize: 13,
      // Extra line height keeps descenders (g, p, y) from being clipped by
      // the fixed-height rows of the xterm renderer.
      lineHeight: 1.25,
      scrollback: 5000,
      theme: {
        background: cssVar("--background", "#000000"),
        foreground: cssVar("--foreground", "#ffffff"),
        cursor: cssVar("--foreground", "#ffffff"),
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(container);
    try {
      fit.fit();
    } catch {
      // container not measurable yet (e.g. jsdom)
    }

    const terminalId = useTerminalStore.getState().terminalId;
    const socket = new WebSocket(
      terminalSocketUrl(window.location, {
        terminalId,
        cols: term.cols,
        rows: term.rows,
      }),
    );
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;

    const send = (payload: Record<string, unknown>) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload));
    };

    socket.onmessage = (event: MessageEvent) => {
      if (typeof event.data === "string") {
        const message = JSON.parse(event.data) as {
          type: string;
          terminal_id?: string;
          code?: number | null;
          message?: string;
        };
        if (message.type === "ready" && message.terminal_id) {
          useTerminalStore.getState().setTerminalId(message.terminal_id);
          setStatus("connected");
        } else if (message.type === "exit") {
          setStatus("exited");
          useTerminalStore.getState().setTerminalId(null);
          term.write(`\r\n[process exited${message.code != null ? ` with code ${message.code}` : ""}]\r\n`);
        } else if (message.type === "error") {
          term.write(`\r\n[terminal error: ${message.message ?? "unknown"}]\r\n`);
        }
        return;
      }
      term.write(new Uint8Array(event.data as ArrayBuffer));
    };
    socket.onclose = () => {
      setStatus((current) => (current === "exited" ? current : "disconnected"));
    };

    const dataSub = term.onData((data) => send({ type: "input", data }));
    const resizeSub = term.onResize(({ cols, rows }) => send({ type: "resize", cols, rows }));
    const observer = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(() => {
          try {
            fit.fit();
          } catch {
            // ignore
          }
        });
    observer?.observe(container);
    term.focus();

    return () => {
      observer?.disconnect();
      dataSub.dispose();
      resizeSub.dispose();
      socket.onclose = null;
      socket.close();
      socketRef.current = null;
      term.dispose();
    };
  }, [generation]);

  // Run snippets requested from elsewhere in the UI once connected.
  useEffect(() => {
    if (!pendingRun || status !== "connected") return;
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "input", data: snippetToTerminalInput(pendingRun.command) }));
    consumeRun(pendingRun.id);
  }, [pendingRun, status, consumeRun]);

  const restart = () => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN && status !== "exited") {
      socket.send(JSON.stringify({ type: "close" }));
    }
    useTerminalStore.getState().setTerminalId(null);
    setStatus("connecting");
    setGeneration((value) => value + 1);
  };

  return (
    <aside
      id="terminal-panel"
      className="flex size-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background"
      aria-label="Terminal"
    >
      <header data-panel-header="" className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border bg-sidebar px-3">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="truncate text-sm font-semibold">Terminal</h2>
          <Badge variant={STATUS_VARIANT[status]} size="meta" data-terminal-status={status}>
            {STATUS_LABEL[status]}
          </Badge>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={status === "connected" ? "Restart terminal" : "Reconnect terminal"}
            title={status === "connected" ? "Restart terminal" : "Reconnect terminal"}
            onClick={status === "disconnected" ? () => {
              setStatus("connecting");
              setGeneration((v) => v + 1);
            } : restart}
          >
            <RotateCcwIcon aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Close terminal panel"
            onClick={onClose}
          >
            <XIcon aria-hidden="true" />
          </Button>
        </div>
      </header>
      <div className="min-h-0 min-w-0 flex-1 bg-background p-2">
        <div ref={containerRef} data-terminal-container="" className="size-full" />
      </div>
    </aside>
  );
}
