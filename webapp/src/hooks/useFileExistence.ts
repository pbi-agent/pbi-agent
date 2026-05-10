import { useCallback, useEffect, useMemo, useState } from "react";
import { searchFileMentions } from "../api";

export type FileExistenceStatus = "known" | "unknown";

const fileExistenceCache = new Map<string, FileExistenceStatus>();
const pendingTokenRequests = new Set<string>();
const FILE_EXISTENCE_DEBOUNCE_MS = 750;

function normalizeToken(token: string): string {
  return token.replaceAll("\\ ", " ");
}

function isValidFileToken(token: string): boolean {
  return token.length > 0 && !token.startsWith("/");
}

export function getCachedFileExistence(token: string): FileExistenceStatus | undefined {
  return fileExistenceCache.get(normalizeToken(token));
}

export function useFileExistence(tokens: string[]): {
  isFileKnown: (token: string) => boolean;
  statuses: Map<string, FileExistenceStatus>;
} {
  const normalizedTokens = useMemo(() => {
    return Array.from(new Set(tokens.map(normalizeToken).filter(isValidFileToken))).sort();
  }, [tokens]);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const unresolved = normalizedTokens.filter(
      (token) => !fileExistenceCache.has(token) && !pendingTokenRequests.has(token),
    );
    if (unresolved.length === 0) return;

    const controllers = new Map<string, AbortController>();
    const timer = window.setTimeout(() => {
      for (const token of unresolved) {
        const controller = new AbortController();
        controllers.set(token, controller);
        pendingTokenRequests.add(token);
        void searchFileMentions(token, 8, { signal: controller.signal })
          .then((result) => {
            if (result.items.some((item) => item.path === token)) {
              fileExistenceCache.set(token, "known");
              return;
            }
            if (result.scan_status !== "scanning") {
              fileExistenceCache.set(token, "unknown");
            }
          })
          .catch((error: unknown) => {
            if (error instanceof DOMException && error.name === "AbortError") return;
            fileExistenceCache.set(token, "unknown");
          })
          .finally(() => {
            pendingTokenRequests.delete(token);
            controllers.delete(token);
            setVersion((current) => current + 1);
          });
      }
    }, FILE_EXISTENCE_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      for (const controller of controllers.values()) controller.abort();
      for (const token of unresolved) pendingTokenRequests.delete(token);
    };
  }, [normalizedTokens, version]);

  void version;
  const isFileKnown = useCallback((token: string) => {
    return fileExistenceCache.get(normalizeToken(token)) === "known";
  }, []);

  return { isFileKnown, statuses: new Map(fileExistenceCache) };
}

export function resetFileExistenceForTest(): void {
  fileExistenceCache.clear();
  pendingTokenRequests.clear();
}
