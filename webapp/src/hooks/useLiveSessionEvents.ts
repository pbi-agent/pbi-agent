import { useEffect, useRef } from "react";
import { websocketUrl } from "../api";
import { useSessionStore } from "../store";
import type { WebEvent } from "../types";

const INITIAL_DELAY = 1000;
const MAX_DELAY = 30000;

export function useLiveSessionEvents(
  sessionKey: string | null,
  liveSessionId: string | null,
): void {
  const applyEvent = useSessionStore((state) => state.applyEvent);
  const setConnection = useSessionStore((state) => state.setConnection);
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

    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    function connect() {
      if (disposed) return;
      setConnection(currentSessionKey, "connecting");
      socket = new WebSocket(websocketUrl(`/api/events/${currentLiveSessionId}`));

      socket.onopen = () => {
        retryDelay.current = INITIAL_DELAY;
        setConnection(currentSessionKey, "connected");
      };

      socket.onmessage = (message) => {
        if (typeof message.data !== "string") {
          return;
        }
        applyEvent(
          currentSessionKey,
          JSON.parse(message.data) as WebEvent,
          currentLiveSessionId,
        );
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
  }, [applyEvent, sessionKey, liveSessionId, setConnection]);
}
