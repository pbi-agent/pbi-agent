import { useLiveSessionEvents } from "./useLiveSessionEvents";

export function useSessionEvents(
  sessionKey: string | null,
  sessionId: string | null,
  fallbackLiveSessionId: string | null = null,
): void {
  useLiveSessionEvents(sessionKey, fallbackLiveSessionId, sessionId);
}
