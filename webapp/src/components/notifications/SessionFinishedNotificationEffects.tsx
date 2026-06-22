import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

import {
  shouldNotifyForWindowState,
  triggerDesktopAndSoundNotification,
} from "../../lib/notificationEffects";
import { useNotificationPreferences } from "../../lib/notificationPreferences";
import { useSessionStore, type SessionRuntimeState } from "../../store";

function sessionDestination(session: SessionRuntimeState): string {
  if (session.sessionId) {
    return `/sessions/${encodeURIComponent(session.sessionId)}`;
  }
  return "/sessions";
}

function sessionIdentity(session: SessionRuntimeState, sessionKey: string): string {
  return session.liveSessionId ?? session.sessionId ?? sessionKey;
}

// A live interactive session worker runs a multi-turn loop, so a successful turn
// never emits `live_session_ended`. The global SessionEndedNotificationEffects
// therefore only covers terminated/errored sessions; this store-driven effect
// fills the gap by notifying when an active session finishes its work and
// re-enables input without a pending question or fatal error.
function isSessionWorking(session: SessionRuntimeState): boolean {
  return session.processing !== null;
}

function isSessionTerminated(session: SessionRuntimeState): boolean {
  return session.sessionEnded || Boolean(session.fatalError) || !session.liveSessionId;
}

function isSessionReadyAfterWork(session: SessionRuntimeState): boolean {
  return session.inputEnabled && !session.pendingUserQuestions;
}

function createSessionFinishedNotificationRequest(session: SessionRuntimeState, identity: string) {
  return {
    title: "pbi-agent session finished",
    body: "A session finished while this tab was hidden or unfocused.",
    destination: sessionDestination(session),
    tag: `session-finished:${identity}`,
  };
}

export function SessionFinishedNotificationEffects() {
  const navigate = useNavigate();
  const preferences = useNotificationPreferences();
  const sessionsByKey = useSessionStore((state) => state.sessionsByKey);
  const workingSessionIdentitiesRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const workingSessionIdentities = workingSessionIdentitiesRef.current;

    for (const [sessionKey, session] of Object.entries(sessionsByKey)) {
      const identity = sessionIdentity(session, sessionKey);

      if (isSessionTerminated(session)) {
        // Errored/ended sessions are handled by SessionEndedNotificationEffects.
        workingSessionIdentities.delete(identity);
        continue;
      }

      if (isSessionWorking(session)) {
        workingSessionIdentities.add(identity);
        continue;
      }

      if (!isSessionReadyAfterWork(session)) {
        // Transient state (e.g. processing cleared before input re-enabled, or a
        // pending question). Keep the working marker so we can notify once the
        // session actually settles into a ready state.
        continue;
      }

      if (!workingSessionIdentities.has(identity)) {
        // The session reached a ready state without us observing it work first
        // (e.g. a freshly hydrated idle session), so there is nothing to announce.
        continue;
      }
      workingSessionIdentities.delete(identity);

      if (!preferences.desktopEnabled && !preferences.soundEnabled) {
        continue;
      }
      if (!shouldNotifyForWindowState()) {
        continue;
      }

      triggerDesktopAndSoundNotification(
        createSessionFinishedNotificationRequest(session, identity),
        preferences,
        navigate,
      );
    }
  }, [navigate, preferences, sessionsByKey]);

  return null;
}
