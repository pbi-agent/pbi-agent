import { useEffect, useMemo, useReducer, useRef } from "react";
import { useNavigate } from "react-router-dom";

import {
  getBrowserNotificationPermission,
  playUserQuestionNotificationSound,
  useNotificationPreferences,
} from "../../lib/notificationPreferences";
import { useSessionStore, type SessionRuntimeState } from "../../store";

type PendingUserQuestionNotification = {
  dedupeKey: string;
  destination: string;
  questionCount: number;
};

function shouldNotifyForWindowState(): boolean {
  return document.visibilityState === "hidden" || !document.hasFocus();
}

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

function createDesktopNotification(
  pending: PendingUserQuestionNotification,
  navigate: ReturnType<typeof useNavigate>,
): void {
  const questionLabel = pending.questionCount === 1 ? "question" : "questions";
  const options: NotificationOptions & { renotify?: boolean } = {
    body: `Assistant is waiting for ${pending.questionCount} ${questionLabel}.`,
    icon: "/logo.jpg",
    renotify: true,
    tag: `ask-user:${pending.dedupeKey}`,
  };
  const notification = new Notification("pbi-agent needs input", options);

  notification.onclick = () => {
    window.focus();
    void navigate(pending.destination);
    notification.close();
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

      let attemptedNotification = false;
      if (
        preferences.desktopEnabled
        && getBrowserNotificationPermission() === "granted"
      ) {
        attemptedNotification = true;
        try {
          createDesktopNotification(pending, navigate);
        } catch {
          // Browser notification construction can fail in restricted contexts.
        }
      }

      if (preferences.soundEnabled) {
        attemptedNotification = true;
        void playUserQuestionNotificationSound();
      }

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
