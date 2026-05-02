import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { websocketUrl } from "../api";
import {
  shouldNotifyForWindowState,
  triggerDesktopAndSoundNotification,
} from "../lib/notificationEffects";
import { useNotificationPreferences, type NotificationPreferences } from "../lib/notificationPreferences";
import type { LiveSession, WebEvent } from "../types";

const INITIAL_DELAY = 1000;
const MAX_DELAY = 30000;

function liveSessionDestination(liveSession: Pick<LiveSession, "live_session_id" | "session_id">): string {
  if (liveSession.session_id) {
    return `/sessions/${encodeURIComponent(liveSession.session_id)}`;
  }
  return `/sessions/live/${encodeURIComponent(liveSession.live_session_id)}`;
}

function readEndedLiveSession(event: WebEvent): LiveSession | null {
  if (event.type !== "live_session_ended") return null;
  const rawLiveSession = event.payload.live_session;
  if (!rawLiveSession || typeof rawLiveSession !== "object") return null;
  const liveSession = rawLiveSession as Partial<LiveSession>;
  if (typeof liveSession.live_session_id !== "string") return null;
  return liveSession as LiveSession;
}

function eventCreatedAtOrAfter(event: WebEvent, timestampMs: number): boolean {
  const createdAtMs = Date.parse(event.created_at);
  return Number.isNaN(createdAtMs) || createdAtMs >= timestampMs;
}

function notifyForEndedLiveSession(
  event: WebEvent,
  preferences: NotificationPreferences,
  notifiedLiveSessionIds: Set<string>,
  connectedAtMs: number,
  navigate: (destination: string) => void | Promise<void>,
): void {
  const liveSession = readEndedLiveSession(event);
  if (!liveSession) return;
  if (notifiedLiveSessionIds.has(liveSession.live_session_id)) return;
  notifiedLiveSessionIds.add(liveSession.live_session_id);

  if (!eventCreatedAtOrAfter(event, connectedAtMs)) return;
  if (!preferences.desktopEnabled && !preferences.soundEnabled) return;
  if (!shouldNotifyForWindowState()) return;

  const endedWithError = Boolean(liveSession.fatal_error);
  triggerDesktopAndSoundNotification(
    {
      title: endedWithError ? "pbi-agent session failed" : "pbi-agent session finished",
      body: endedWithError
        ? "A session ended with an error."
        : "A session finished while this tab was hidden or unfocused.",
      destination: liveSessionDestination(liveSession),
      tag: `session-ended:${liveSession.live_session_id}`,
    },
    preferences,
    navigate,
  );
}

export function useTaskEvents(): void {
  const client = useQueryClient();
  const navigate = useNavigate();
  const preferences = useNotificationPreferences();
  const preferencesRef = useRef(preferences);
  const navigateRef = useRef(navigate);
  const retryDelay = useRef(INITIAL_DELAY);
  const notifiedLiveSessionIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    preferencesRef.current = preferences;
  }, [preferences]);

  useEffect(() => {
    navigateRef.current = navigate;
  }, [navigate]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    function connect() {
      if (disposed) return;
      const connectedAtMs = Date.now();
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
          if (event.type === "live_session_ended") {
            notifyForEndedLiveSession(
              event,
              preferencesRef.current,
              notifiedLiveSessionIds.current,
              connectedAtMs,
              (destination) => navigateRef.current(destination),
            );
          }
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
