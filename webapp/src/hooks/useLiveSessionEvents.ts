import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { websocketUrl } from "../api";
import { useSessionStore } from "../store";
import type { WebEvent } from "../types";

const INITIAL_DELAY = 1000;
const MAX_DELAY = 30000;

export function useLiveSessionEvents(
  sessionKey: string | null,
  liveSessionId: string | null,
  sessionId: string | null = null,
): void {
  const applyEvent = useSessionStore((state) => state.applyEvent);
  const setConnection = useSessionStore((state) => state.setConnection);
  const queryClient = useQueryClient();
  const retryDelay = useRef(INITIAL_DELAY);

  useEffect(() => {
    if (!sessionKey || !liveSessionId) {
      if (sessionKey) {
        setConnection(sessionKey, "disconnected");
      }
      return;
    }
    const currentSessionKey = sessionKey;
    const currentLiveSessionId = liveSessionId;
    const currentSessionId = sessionId;

    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    function connect() {
      if (disposed) return;
      setConnection(currentSessionKey, "connecting");
      const since = useSessionStore.getState().sessionsByKey[currentSessionKey]?.lastEventSeq ?? 0;
      const eventPath = currentSessionId
        ? `/api/events/sessions/${encodeURIComponent(currentSessionId)}`
        : `/api/events/${currentLiveSessionId}`;
      socket = new WebSocket(websocketUrl(`${eventPath}?since=${since}`));

      socket.onopen = () => {
        retryDelay.current = INITIAL_DELAY;
        setConnection(currentSessionKey, "connected");
      };

      socket.onmessage = (message) => {
        if (typeof message.data !== "string") {
          return;
        }
        const event = JSON.parse(message.data) as WebEvent;
        const resolvedLiveSessionId = readLiveSessionId(event) ?? currentLiveSessionId;
        const targetSessionKey = resolvedLiveSessionId
          ? useSessionStore.getState().liveSessionIndex[resolvedLiveSessionId] ?? currentSessionKey
          : currentSessionKey;
        const wasInputEnabled = readCurrentInputEnabled(
          event,
          targetSessionKey,
          resolvedLiveSessionId ?? "",
        );
        const resolvedSessionKey = applyEvent(
          targetSessionKey,
          event,
          resolvedLiveSessionId,
        );
        if (shouldRefreshRunQueries(event, wasInputEnabled)) {
          const sessionId = resolveSessionId(
            event,
            resolvedSessionKey,
            resolvedLiveSessionId ?? "",
          );
          if (sessionId) {
            void queryClient.invalidateQueries({ queryKey: ["session-runs", sessionId] });
          }
          void queryClient.invalidateQueries({ queryKey: ["run-detail"] });
        }
      };

      socket.onclose = () => {
        if (disposed) return;
        setConnection(currentSessionKey, "disconnected");
        retryTimer = setTimeout(() => {
          retryDelay.current = Math.min(retryDelay.current * 2, MAX_DELAY);
          connect();
        }, retryDelay.current);
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, [applyEvent, queryClient, sessionKey, liveSessionId, sessionId, setConnection]);
}

function shouldRefreshRunQueries(event: WebEvent, wasInputEnabled: boolean | null): boolean {
  if (event.type === "input_state") {
    return event.payload.enabled === true && wasInputEnabled === false;
  }
  if (event.type === "session_state") {
    return event.payload.state === "ended";
  }
  return false;
}

function readCurrentInputEnabled(
  event: WebEvent,
  currentSessionKey: string,
  currentLiveSessionId: string,
): boolean | null {
  if (event.type !== "input_state") {
    return null;
  }
  const store = useSessionStore.getState();
  const eventSessionId = readSessionId(event);
  const storeResolvedKey = eventSessionId
    ? store.sessionIndex[eventSessionId] ?? `session:${eventSessionId}`
    : store.liveSessionIndex[currentLiveSessionId]
      ?? findSessionKeyByLiveSessionId(currentLiveSessionId, store.sessionsByKey)
      ?? currentSessionKey;
  return store.sessionsByKey[storeResolvedKey]?.inputEnabled ?? null;
}

function resolveSessionId(
  event: WebEvent,
  resolvedSessionKey: string,
  currentLiveSessionId: string,
): string | null {
  const eventSessionId = readSessionId(event);
  if (eventSessionId) {
    return eventSessionId;
  }

  const store = useSessionStore.getState();
  const storeResolvedKey =
    store.liveSessionIndex[currentLiveSessionId]
    ?? findSessionKeyByLiveSessionId(currentLiveSessionId, store.sessionsByKey)
    ?? resolvedSessionKey;
  return store.sessionsByKey[storeResolvedKey]?.sessionId ?? null;
}

function findSessionKeyByLiveSessionId(
  liveSessionId: string,
  sessionsByKey: ReturnType<typeof useSessionStore.getState>["sessionsByKey"],
): string | null {
  return Object.entries(sessionsByKey).find(([, session]) => (
    session.liveSessionId === liveSessionId
  ))?.[0] ?? null;
}

function readSessionId(event: WebEvent): string | null {
  return typeof event.payload.session_id === "string" ? event.payload.session_id : null;
}

function readLiveSessionId(event: WebEvent): string | null {
  return typeof event.payload.live_session_id === "string" ? event.payload.live_session_id : null;
}
