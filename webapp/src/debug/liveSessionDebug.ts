import type { ConnectionState } from "../store";

export type LiveSessionDebugEntry = {
  sessionKey: string;
  sessionId: string | null;
  liveSessionId: string | null;
  clientStreamId: string | null;
  eventPath: string | null;
  url: string | null;
  requestedSince: number;
  cursor: number;
  connection: ConnectionState;
  recoveryReason: string | null;
  recovery: Record<string, unknown> | null;
  lastEvent: Record<string, unknown> | null;
  reconnect: { scheduled: boolean; retryDelayMs: number | null };
  openedAt: string | null;
  updatedAt: string;
  closedAt: string | null;
  disposed: boolean;
};

export type LiveSessionDebugState = {
  sessions: Record<string, LiveSessionDebugEntry>;
};

declare global {
  interface Window {
    __PBI_AGENT_LIVE_DEBUG__?: LiveSessionDebugState;
  }
}

let streamCounter = 0;

export function nextClientStreamId(): string {
  streamCounter += 1;
  return `sse:${streamCounter}`;
}

export function updateLiveSessionDebug(
  sessionKey: string,
  patch: Partial<LiveSessionDebugEntry>,
): void {
  if (!debugEnabled()) return;
  const now = new Date().toISOString();
  const state = window.__PBI_AGENT_LIVE_DEBUG__ ?? { sessions: {} };
  const current = state.sessions[sessionKey] ?? emptyEntry(sessionKey, now);
  state.sessions[sessionKey] = {
    ...current,
    ...patch,
    updatedAt: now,
  };
  window.__PBI_AGENT_LIVE_DEBUG__ = state;
}

function emptyEntry(sessionKey: string, now: string): LiveSessionDebugEntry {
  return {
    sessionKey,
    sessionId: null,
    liveSessionId: null,
    clientStreamId: null,
    eventPath: null,
    url: null,
    requestedSince: 0,
    cursor: 0,
    connection: "disconnected",
    recoveryReason: null,
    recovery: null,
    lastEvent: null,
    reconnect: { scheduled: false, retryDelayMs: null },
    openedAt: null,
    updatedAt: now,
    closedAt: null,
    disposed: false,
  };
}

function debugEnabled(): boolean {
  return import.meta.env.DEV || import.meta.env.MODE === "test";
}
