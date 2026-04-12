import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { websocketUrl } from "../api";
import type { WebEvent } from "../types";

const INITIAL_DELAY = 1000;
const MAX_DELAY = 30000;

export function useTaskEvents(): void {
  const client = useQueryClient();
  const retryDelay = useRef(INITIAL_DELAY);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    function connect() {
      if (disposed) return;
      socket = new WebSocket(websocketUrl("/api/events/app"));

      socket.onopen = () => {
        retryDelay.current = INITIAL_DELAY;
      };

      socket.onmessage = (message) => {
        if (typeof message.data !== "string") {
          return;
        }
        const event = JSON.parse(message.data) as WebEvent;
        if (event.type === "task_updated" || event.type === "task_deleted") {
          void client.invalidateQueries({ queryKey: ["tasks"] });
          return;
        }
        if (event.type === "board_stages_updated") {
          void client.invalidateQueries({ queryKey: ["board-stages"] });
          void client.invalidateQueries({ queryKey: ["tasks"] });
          void client.invalidateQueries({ queryKey: ["bootstrap"] });
          return;
        }
        if (
          event.type === "live_session_started"
          || event.type === "live_session_updated"
          || event.type === "live_session_bound"
          || event.type === "live_session_ended"
        ) {
          void client.invalidateQueries({ queryKey: ["sessions"] });
          void client.invalidateQueries({ queryKey: ["bootstrap"] });
          void client.invalidateQueries({ queryKey: ["live-sessions"] });
        }
      };

      socket.onclose = () => {
        if (disposed) return;
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
  }, [client]);
}
