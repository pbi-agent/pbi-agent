import { useEffect, useMemo, useReducer, useRef } from "react";
import { useNavigate } from "react-router-dom";

import {
  shouldNotifyForWindowState,
  triggerDesktopAndSoundNotification,
} from "../../lib/notificationEffects";
import { useNotificationPreferences } from "../../lib/notificationPreferences";
import { useSessionStore, type SessionRuntimeState } from "../../store";

type PendingUserQuestionNotification = {
  dedupeKey: string;
  destination: string;
  questionCount: number;
};

function sessionDestination(session: SessionRuntimeState): string {
  if (session.sessionId) {
    return `/sessions/${encodeURIComponent(session.sessionId)}`;
  }
  if (session.liveSessionId) {
    return `/sessions/live/${encodeURIComponent(session.liveSessionId)}`;
  }
  return "/sessions";
}

function collectPendingUserQuestionNotifications(
  sessionsByKey: Record<string, SessionRuntimeState>,
): PendingUserQuestionNotification[] {
  return Object.entries(sessionsByKey).flatMap(([sessionKey, session]) => {
    if (!session.pendingUserQuestions) return [];
    const sessionIdentity = session.liveSessionId ?? session.sessionId ?? sessionKey;
    return [{
      dedupeKey: `${sessionIdentity}:${session.pendingUserQuestions.prompt_id}`,
      destination: sessionDestination(session),
      questionCount: session.pendingUserQuestions.questions.length,
    }];
  });
}

function createAskUserNotificationRequest(pending: PendingUserQuestionNotification) {
  const questionLabel = pending.questionCount === 1 ? "question" : "questions";
  return {
    title: "pbi-agent needs input",
    body: `Assistant is waiting for ${pending.questionCount} ${questionLabel}.`,
    destination: pending.destination,
    tag: `ask-user:${pending.dedupeKey}`,
  };
}

export function AskUserNotificationEffects() {
  const navigate = useNavigate();
  const preferences = useNotificationPreferences();
  const sessionsByKey = useSessionStore((state) => state.sessionsByKey);
  const notifiedPromptKeysRef = useRef<Set<string>>(new Set());
  const windowStateVersion = useWindowStateVersion();

  const pendingNotifications = useMemo(
    () => collectPendingUserQuestionNotifications(sessionsByKey),
    [sessionsByKey],
  );

  useEffect(() => {
    if (!preferences.desktopEnabled && !preferences.soundEnabled) return;
    if (!shouldNotifyForWindowState()) return;

    for (const pending of pendingNotifications) {
      if (notifiedPromptKeysRef.current.has(pending.dedupeKey)) {
        continue;
      }

      const attemptedNotification = triggerDesktopAndSoundNotification(
        createAskUserNotificationRequest(pending),
        preferences,
        navigate,
      );

      if (attemptedNotification) {
        notifiedPromptKeysRef.current.add(pending.dedupeKey);
      }
    }
  }, [navigate, pendingNotifications, preferences, windowStateVersion]);

  return null;
}

function useWindowStateVersion(): number {
  const [version, bumpVersion] = useReducer((current: number) => current + 1, 0);

  useEffect(() => {
    document.addEventListener("visibilitychange", bumpVersion);
    window.addEventListener("focus", bumpVersion);
    window.addEventListener("blur", bumpVersion);
    return () => {
      document.removeEventListener("visibilitychange", bumpVersion);
      window.removeEventListener("focus", bumpVersion);
      window.removeEventListener("blur", bumpVersion);
    };
  }, []);

  return version;
}
