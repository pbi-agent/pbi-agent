import { useEffect, useMemo, useSyncExternalStore } from "react";
import { useLocation } from "react-router-dom";

const LAST_OPENED_SESSION_STORAGE_KEY = "pbi-agent.last-opened-session-id";
const LAST_OPENED_SESSION_EVENT = "pbi-agent:last-opened-session-changed";
const SESSION_ROUTE_PATTERN = /^\/sessions\/([^/]+)/;

function safeDecodePathSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function sessionIdFromPathname(pathname: string): string | null {
  const match = SESSION_ROUTE_PATTERN.exec(pathname);
  return match ? safeDecodePathSegment(match[1]) : null;
}

function readLastOpenedSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(LAST_OPENED_SESSION_STORAGE_KEY);
}

function emitLastOpenedSessionChange(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(LAST_OPENED_SESSION_EVENT));
}

function subscribeToLastOpenedSessionChanges(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(LAST_OPENED_SESSION_EVENT, onStoreChange);
  window.addEventListener("storage", onStoreChange);
  return () => {
    window.removeEventListener(LAST_OPENED_SESSION_EVENT, onStoreChange);
    window.removeEventListener("storage", onStoreChange);
  };
}

export function rememberLastOpenedSessionId(sessionId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LAST_OPENED_SESSION_STORAGE_KEY, sessionId);
  emitLastOpenedSessionChange();
}

export function forgetLastOpenedSessionId(sessionId: string): void {
  if (readLastOpenedSessionId() !== sessionId || typeof window === "undefined") return;
  window.localStorage.removeItem(LAST_OPENED_SESSION_STORAGE_KEY);
  emitLastOpenedSessionChange();
}

export function useLastOpenedSessionPath(): string {
  const { pathname } = useLocation();
  const rememberedSessionId = useSyncExternalStore(
    subscribeToLastOpenedSessionChanges,
    readLastOpenedSessionId,
    () => null,
  );
  const routeSessionId = useMemo(() => sessionIdFromPathname(pathname), [pathname]);

  useEffect(() => {
    if (routeSessionId) rememberLastOpenedSessionId(routeSessionId);
  }, [routeSessionId]);

  const lastOpenedSessionId = routeSessionId ?? rememberedSessionId;
  return lastOpenedSessionId
    ? `/sessions/${encodeURIComponent(lastOpenedSessionId)}`
    : "/sessions";
}
