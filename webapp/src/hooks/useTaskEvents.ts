import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { websocketUrl } from "../api";
import type {
  LiveSession,
  LiveSessionLifecycleEvent,
  LiveSessionLifecycleEventType,
  WebEvent,
} from "../types";

const INITIAL_DELAY = 1000;
const MAX_DELAY = 30000;
const MAX_LIVE_SESSION_EVENT_HISTORY = 100;
const LIVE_SESSION_LIFECYCLE_TYPES = new Set<string>([
  "live_session_started",
  "live_session_updated",
  "live_session_bound",
  "live_session_ended",
]);

function isLiveSessionLifecycleType(type: string): type is LiveSessionLifecycleEventType {
  return LIVE_SESSION_LIFECYCLE_TYPES.has(type);
}

function isLiveSession(value: unknown): value is LiveSession {
  return (
    typeof value === "object"
    && value !== null
    && typeof (value as { live_session_id?: unknown }).live_session_id === "string"
    && typeof (value as { status?: unknown }).status === "string"
  );
}

function lifecycleEventFromWebEvent(event: WebEvent): LiveSessionLifecycleEvent | null {
  if (!isLiveSessionLifecycleType(event.type)) {
    return null;
  }
  const liveSession = event.payload.live_session;
  if (!isLiveSession(liveSession)) {
    return null;
  }
  return {
    seq: event.seq,
    type: event.type,
    created_at: event.created_at,
    live_session: liveSession,
  };
}

function eventCreatedAtOrAfter(event: WebEvent, timestampMs: number): boolean {
  const eventCreatedAtMs = Date.parse(event.created_at);
  return Number.isFinite(eventCreatedAtMs) && eventCreatedAtMs >= timestampMs;
}

export function useTaskEvents(): LiveSessionLifecycleEvent[] {
  const client = useQueryClient();
  const retryDelay = useRef(INITIAL_DELAY);
  const startedAtMs = useRef<number | null>(null);
  const latestHandledSeq = useRef(0);
  const [liveSessionEvents, setLiveSessionEvents] = useState<LiveSessionLifecycleEvent[]>([]);

  useEffect(() => {
    if (startedAtMs.current === null) {
      startedAtMs.current = Date.now();
    }
    const hookStartedAtMs = startedAtMs.current;
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
        if (event.type === "session_updated") {
          void client.invalidateQueries({ queryKey: ["sessions"] });
          void client.invalidateQueries({ queryKey: ["bootstrap"] });
          const session = event.payload.session as { session_id?: unknown } | undefined;
          if (typeof session?.session_id === "string") {
            void client.invalidateQueries({ queryKey: ["session", session.session_id] });
          }
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
          const latestSeq = latestHandledSeq.current;
          latestHandledSeq.current = Math.max(latestSeq, event.seq);
          if (
            event.seq <= latestSeq
            || !eventCreatedAtOrAfter(event, hookStartedAtMs)
          ) {
            return;
          }
          const lifecycleEvent = lifecycleEventFromWebEvent(event);
          if (lifecycleEvent) {
            setLiveSessionEvents((previous) => [
              ...previous,
              lifecycleEvent,
            ].slice(-MAX_LIVE_SESSION_EVENT_HISTORY));
          }
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

  return liveSessionEvents;
}
