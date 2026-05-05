import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { eventStreamUrl } from "../api";
import { nextClientStreamId, updateLiveSessionDebug } from "../debug/liveSessionDebug";
import { parseSseEvent } from "../events";
import { resolveSessionEventTarget, useSessionStore } from "../store";
import type { WebEvent } from "../types";

const INITIAL_DELAY = 1000;
const MAX_DELAY = 30000;

export function useLiveSessionEvents(
  sessionKey: string | null,
  liveSessionId: string | null,
  sessionId: string | null = null,
): void {
  const applyEvent = useSessionStore((state) => state.applyEvent);
  const resetStreamState = useSessionStore((state) => state.resetStreamState);
  const setConnection = useSessionStore((state) => state.setConnection);
  const queryClient = useQueryClient();
  const retryDelay = useRef(INITIAL_DELAY);

  useEffect(() => {
    if (!sessionKey || !liveSessionId) {
      if (sessionKey) {
        setConnection(sessionKey, "disconnected");
        updateLiveSessionDebug(sessionKey, {
          sessionId,
          liveSessionId,
          connection: "disconnected",
          disposed: true,
          closedAt: new Date().toISOString(),
        });
      }
      return;
    }
    const currentSessionKey = sessionKey;
    const currentLiveSessionId = liveSessionId;
    const currentSessionId = sessionId;

    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;
    let hasOpened = false;
    let recoveryMode = false;

    function scheduleReconnect(currentSource: EventSource) {
      if (!disposed && source === currentSource && !retryTimer) {
        updateLiveSessionDebug(currentSessionKey, {
          reconnect: { scheduled: true, retryDelayMs: retryDelay.current },
        });
        retryTimer = setTimeout(() => {
          retryTimer = null;
          retryDelay.current = Math.min(retryDelay.current * 2, MAX_DELAY);
          connect();
        }, retryDelay.current);
      }
    }

    function recoverFromSnapshot(
      currentSource: EventSource,
      targetSessionKey: string,
      targetSessionId: string | null,
      recoveryReason: string,
      recovery: Record<string, unknown> | null,
    ) {
      const isCurrentStreamTarget = targetSessionKey === currentSessionKey;
      if (isCurrentStreamTarget) {
        recoveryMode = true;
      }
      setConnection(targetSessionKey, "recovering");
      updateLiveSessionDebug(targetSessionKey, {
        connection: "recovering",
        recoveryReason,
        recovery,
      });
      if (isCurrentStreamTarget) {
        currentSource.close();
      }
      const invalidations = [
        queryClient.invalidateQueries({ queryKey: ["sessions"] }),
        queryClient.invalidateQueries({ queryKey: ["bootstrap"] }),
        queryClient.invalidateQueries({ queryKey: ["run-detail"] }),
      ];
      if (targetSessionId) {
        invalidations.push(
          queryClient.invalidateQueries({ queryKey: ["session", targetSessionId] }),
          queryClient.invalidateQueries({ queryKey: ["session-runs", targetSessionId] }),
        );
      }
      void Promise.all(invalidations)
        .then(() => {
          if (disposed || source !== currentSource) return;
          resetStreamState(targetSessionKey, { preserveLiveSession: true });
          if (isCurrentStreamTarget) {
            setConnection(targetSessionKey, "recovering");
            scheduleReconnect(currentSource);
            return;
          }
          recoveryMode = false;
          setConnection(targetSessionKey, "disconnected");
          updateLiveSessionDebug(targetSessionKey, {
            connection: "disconnected",
            recoveryReason: `${recoveryReason}-cross-target-refetch`,
          });
        })
        .catch(() => {
          if (disposed || source !== currentSource) return;
          setConnection(targetSessionKey, "recovery_failed");
          updateLiveSessionDebug(targetSessionKey, {
            connection: "recovery_failed",
            recoveryReason: "snapshot-invalidation-failed",
          });
          if (isCurrentStreamTarget) {
            scheduleReconnect(currentSource);
            return;
          }
          recoveryMode = false;
        });
    }

    function connect() {
      if (disposed) return;
      setConnection(
        currentSessionKey,
        recoveryMode ? "recovering" : hasOpened ? "reconnecting" : "connecting",
      );
      const since = useSessionStore.getState().sessionsByKey[currentSessionKey]?.lastEventSeq ?? 0;
      const eventPath = currentSessionId
        ? `/api/events/sessions/${encodeURIComponent(currentSessionId)}`
        : `/api/events/${currentLiveSessionId}`;
      const params = new URLSearchParams({ since: String(since) });
      if (currentSessionId) {
        params.set("live_session_id", currentLiveSessionId);
      }
      const url = eventStreamUrl(`${eventPath}?${params.toString()}`);
      const currentSource = new EventSource(url);
      source = currentSource;
      const clientStreamId = nextClientStreamId();
      updateLiveSessionDebug(currentSessionKey, {
        sessionId: currentSessionId,
        liveSessionId: currentLiveSessionId,
        clientStreamId,
        eventPath,
        url,
        requestedSince: since,
        cursor: since,
        connection: recoveryMode ? "recovering" : hasOpened ? "reconnecting" : "connecting",
        reconnect: { scheduled: false, retryDelayMs: null },
        disposed: false,
        closedAt: null,
      });

      currentSource.onopen = () => {
        if (disposed || source !== currentSource) return;
        retryDelay.current = INITIAL_DELAY;
        const nextConnection = hasOpened || recoveryMode ? "recovered" : "connected";
        hasOpened = true;
        recoveryMode = false;
        setConnection(currentSessionKey, nextConnection);
        updateLiveSessionDebug(currentSessionKey, {
          connection: nextConnection,
          cursor: useSessionStore.getState().sessionsByKey[currentSessionKey]?.lastEventSeq ?? 0,
          openedAt: new Date().toISOString(),
        });
      };

      currentSource.onmessage = (message) => {
        if (disposed || source !== currentSource) return;
        if (typeof message.data !== "string") return;
        const event = parseSseEvent(message.data);
        if (!event) return;
        if (event.type === "server.connected" || event.type === "server.heartbeat") return;
        if (
          event.type === "server.replay_incomplete"
          && event.payload.snapshot_required === true
        ) {
          const resolvedLiveSessionId = readLiveSessionId(event) ?? currentLiveSessionId;
          const store = useSessionStore.getState();
          const target = resolveSessionEventTarget(
            store,
            currentSessionKey,
            event,
            resolvedLiveSessionId,
          );
          const targetSessionKey = target.sessionKey;
          const targetSessionId = readSessionId(event)
            ?? currentSessionId
            ?? store.sessionsByKey[targetSessionKey]?.sessionId
            ?? null;
          recoverFromSnapshot(
            currentSource,
            targetSessionKey,
            targetSessionId,
            String(event.payload.reason),
            {
              requestedSince: event.payload.requested_since,
              resolvedSince: event.payload.resolved_since,
              oldestAvailableSeq: event.payload.oldest_available_seq,
              latestSeq: event.payload.latest_seq,
              snapshotRequired: event.payload.snapshot_required,
            },
          );
          return;
        }
        const resolvedLiveSessionId = readLiveSessionId(event) ?? currentLiveSessionId;
        const targetSessionKey = resolveSessionEventTarget(
          useSessionStore.getState(),
          currentSessionKey,
          event,
          resolvedLiveSessionId,
        ).sessionKey;
        const wasInputEnabled = readCurrentInputEnabled(
          event,
          targetSessionKey,
          resolvedLiveSessionId ?? "",
        );
        const applyResult = applyEvent(
          targetSessionKey,
          event,
          resolvedLiveSessionId,
        );
        updateLiveSessionDebug(applyResult.sessionKey, {
          cursor: useSessionStore.getState().sessionsByKey[applyResult.sessionKey]?.lastEventSeq ?? 0,
          lastEvent: {
            seq: event.seq,
            type: event.type,
            createdAt: event.created_at,
            targetSessionKey: applyResult.sessionKey,
            resolvedSessionId: readSessionId(event),
            resolvedLiveSessionId,
            applied: applyResult.applied,
            applyReason: applyResult.reason,
          },
        });
        if (applyResult.reloadRequired) {
          const targetSessionId = readSessionId(event)
            ?? currentSessionId
            ?? useSessionStore.getState().sessionsByKey[applyResult.sessionKey]?.sessionId
            ?? null;
          recoverFromSnapshot(
            currentSource,
            applyResult.sessionKey,
            targetSessionId,
            applyResult.reason ?? "sequence-gap",
            null,
          );
          return;
        }
        if (shouldRefreshRunQueries(event, wasInputEnabled)) {
          const sessionId = resolveSessionId(
            event,
            applyResult.sessionKey,
            resolvedLiveSessionId ?? "",
          );
          if (sessionId) {
            void queryClient.invalidateQueries({ queryKey: ["session-runs", sessionId] });
          }
          void queryClient.invalidateQueries({ queryKey: ["run-detail"] });
        }
      };

      currentSource.onerror = () => {
        if (disposed || source !== currentSource || retryTimer) return;
        currentSource.close();
        setConnection(currentSessionKey, hasOpened ? "reconnecting" : "disconnected");
        updateLiveSessionDebug(currentSessionKey, {
          connection: hasOpened ? "reconnecting" : "disconnected",
          closedAt: new Date().toISOString(),
        });
        scheduleReconnect(currentSource);
      };
    }

    connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      source?.close();
      updateLiveSessionDebug(currentSessionKey, {
        disposed: true,
        closedAt: new Date().toISOString(),
      });
    };
  }, [applyEvent, queryClient, resetStreamState, sessionKey, liveSessionId, sessionId, setConnection]);
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
  return "session_id" in event.payload && typeof event.payload.session_id === "string"
    ? event.payload.session_id
    : null;
}

function readLiveSessionId(event: WebEvent): string | null {
  return "live_session_id" in event.payload && typeof event.payload.live_session_id === "string"
    ? event.payload.live_session_id
    : null;
}
