import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

import {
  shouldNotifyForWindowState,
  triggerDesktopAndSoundNotification,
} from "../../lib/notificationEffects";
import { useNotificationPreferences } from "../../lib/notificationPreferences";
import type { LiveSession, LiveSessionLifecycleEvent } from "../../types";

type SessionEndedNotificationEffectsProps = {
  liveSessionEvents?: LiveSessionLifecycleEvent[];
  liveSessions: LiveSession[];
};

function isActiveLiveSession(liveSession: LiveSession): boolean {
  return liveSession.status === "starting" || liveSession.status === "running";
}

function liveSessionDestination(liveSession: Pick<LiveSession, "live_session_id" | "session_id">): string {
  if (liveSession.session_id) {
    return `/sessions/${encodeURIComponent(liveSession.session_id)}`;
  }
  return "/sessions";
}

function createSessionEndedNotificationRequest(liveSession: LiveSession) {
  const endedWithError = Boolean(liveSession.fatal_error);
  return {
    title: endedWithError ? "pbi-agent session failed" : "pbi-agent session finished",
    body: endedWithError
      ? "A session ended with an error."
      : "A session finished while this tab was hidden or unfocused.",
    destination: liveSessionDestination(liveSession),
    tag: `session-ended:${liveSession.live_session_id}`,
  };
}

export function SessionEndedNotificationEffects({
  liveSessionEvents = [],
  liveSessions,
}: SessionEndedNotificationEffectsProps) {
  const navigate = useNavigate();
  const preferences = useNotificationPreferences();
  const observedActiveLiveSessionIdsRef = useRef<Set<string>>(new Set());
  const handledEndedLiveSessionIdsRef = useRef<Set<string>>(new Set());
  const handledLifecycleEventSeqsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    const observedActiveLiveSessionIds = observedActiveLiveSessionIdsRef.current;
    const handledEndedLiveSessionIds = handledEndedLiveSessionIdsRef.current;
    const handledLifecycleEventSeqs = handledLifecycleEventSeqsRef.current;

    function handleEndedLiveSession(liveSession: LiveSession) {
      const liveSessionId = liveSession.live_session_id;
      if (handledEndedLiveSessionIds.has(liveSessionId)) {
        return;
      }

      const wasObservedActive = observedActiveLiveSessionIds.has(liveSessionId);
      handledEndedLiveSessionIds.add(liveSessionId);
      observedActiveLiveSessionIds.delete(liveSessionId);

      if (!wasObservedActive) {
        return;
      }
      if (!preferences.desktopEnabled && !preferences.soundEnabled) {
        return;
      }
      if (!shouldNotifyForWindowState()) {
        return;
      }

      triggerDesktopAndSoundNotification(
        createSessionEndedNotificationRequest(liveSession),
        preferences,
        navigate,
      );
    }

    for (const event of liveSessionEvents) {
      if (handledLifecycleEventSeqs.has(event.seq)) {
        continue;
      }
      handledLifecycleEventSeqs.add(event.seq);

      const liveSession = event.live_session;
      if (isActiveLiveSession(liveSession)) {
        observedActiveLiveSessionIds.add(liveSession.live_session_id);
        continue;
      }

      if (event.type === "live_session_ended" || liveSession.status === "ended") {
        handleEndedLiveSession(liveSession);
      }
    }

    for (const liveSession of liveSessions) {
      if (isActiveLiveSession(liveSession)) {
        observedActiveLiveSessionIds.add(liveSession.live_session_id);
        continue;
      }

      if (liveSession.status !== "ended") {
        continue;
      }
      handleEndedLiveSession(liveSession);
    }
  }, [liveSessionEvents, liveSessions, navigate, preferences]);

  return null;
}
