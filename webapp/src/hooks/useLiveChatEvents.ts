import { useEffect, useRef } from "react";
import { websocketUrl } from "../api";
import { useChatStore } from "../store";
import type { WebEvent } from "../types";

const INITIAL_DELAY = 1000;
const MAX_DELAY = 30000;

export function useLiveChatEvents(
  chatKey: string | null,
  liveSessionId: string | null,
): void {
  const applyEvent = useChatStore((state) => state.applyEvent);
  const setConnection = useChatStore((state) => state.setConnection);
  const retryDelay = useRef(INITIAL_DELAY);

  useEffect(() => {
    if (!chatKey || !liveSessionId) {
      if (chatKey) {
        setConnection(chatKey, "disconnected");
      }
      return;
    }

    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    function connect() {
      if (disposed) return;
      setConnection(chatKey, "connecting");
      socket = new WebSocket(websocketUrl(`/api/events/${liveSessionId}`));

      socket.onopen = () => {
        retryDelay.current = INITIAL_DELAY;
        setConnection(chatKey, "connected");
      };

      socket.onmessage = (message) => {
        applyEvent(chatKey, JSON.parse(message.data) as WebEvent);
      };

      socket.onclose = () => {
        if (disposed) return;
        setConnection(chatKey, "disconnected");
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
  }, [applyEvent, chatKey, liveSessionId, setConnection]);
}
