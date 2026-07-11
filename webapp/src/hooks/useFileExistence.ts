import { useCallback, useEffect, useMemo, useState } from "react";
import { searchFileMentions } from "../api";

export type FileExistenceStatus = "known" | "unknown";

type FileExistenceOptions = {
  workspaceKey?: string | null;
  indexGeneration?: string | null;
  indexRevision?: number | null;
};

type WorkspaceFileExistenceCache = {
  generation: string | null;
  revision: number | null;
  statuses: Map<string, FileExistenceStatus>;
};

const fileExistenceCache = new Map<string, WorkspaceFileExistenceCache>();
const pendingTokenRequests = new Set<string>();
const FILE_EXISTENCE_DEBOUNCE_MS = 750;
const DEFAULT_WORKSPACE_KEY = "__default_workspace__";

function normalizeToken(token: string): string {
  return token.replaceAll("\\ ", " ");
}

function isValidFileToken(token: string): boolean {
  return token.length > 0 && !token.startsWith("/");
}

function normalizeWorkspaceKey(workspaceKey: string | null | undefined): string {
  return workspaceKey?.trim() || DEFAULT_WORKSPACE_KEY;
}

function statusesFor(
  workspaceKey: string,
  generation: string | null | undefined,
  revision: number | null | undefined,
): Map<string, FileExistenceStatus> {
  const normalizedGeneration = generation ?? null;
  const normalizedRevision = revision ?? null;
  let workspaceCache = fileExistenceCache.get(workspaceKey);
  if (
    !workspaceCache
    || workspaceCache.generation !== normalizedGeneration
    || workspaceCache.revision !== normalizedRevision
  ) {
    workspaceCache = {
      generation: normalizedGeneration,
      revision: normalizedRevision,
      statuses: new Map(),
    };
    fileExistenceCache.set(workspaceKey, workspaceCache);
  }
  return workspaceCache.statuses;
}

function statusesForResponse(
  workspaceKey: string,
  generation: string,
  revision: number,
): Map<string, FileExistenceStatus> {
  const current = fileExistenceCache.get(workspaceKey);
  if (
    current?.generation === generation
    && current.revision !== null
    && current.revision > revision
  ) {
    return current.statuses;
  }
  return statusesFor(workspaceKey, generation, revision);
}

function pendingRequestKey(
  workspaceKey: string,
  generation: string | null | undefined,
  revision: number | null | undefined,
  token: string,
): string {
  return JSON.stringify([
    workspaceKey,
    generation ?? "unknown",
    revision ?? "unknown",
    token,
  ]);
}

export function getCachedFileExistence(
  token: string,
  options: FileExistenceOptions = {},
): FileExistenceStatus | undefined {
  const workspaceKey = normalizeWorkspaceKey(options.workspaceKey);
  return statusesFor(
    workspaceKey,
    options.indexGeneration,
    options.indexRevision,
  ).get(
    normalizeToken(token),
  );
}

export function useFileExistence(
  tokens: string[],
  options: FileExistenceOptions = {},
): {
  isFileKnown: (token: string) => boolean;
  statuses: Map<string, FileExistenceStatus>;
} {
  const workspaceKey = normalizeWorkspaceKey(options.workspaceKey);
  const [observedIndex, setObservedIndex] = useState<{
    workspaceKey: string;
    sourceGeneration: string | null;
    generation: string | null;
    revision: number | null;
  } | null>(null);
  const optionGeneration = options.indexGeneration ?? null;
  const optionRevision = options.indexRevision ?? null;
  const observedIdentity =
    observedIndex?.workspaceKey === workspaceKey
      && observedIndex.sourceGeneration === optionGeneration
      ? observedIndex
      : null;
  const effectiveGeneration =
    observedIdentity?.generation ?? optionGeneration;
  const effectiveRevision =
    observedIdentity === null
      ? optionRevision
      : observedIdentity.generation === optionGeneration
        && optionRevision !== null
        && observedIdentity.revision !== null
        ? Math.max(optionRevision, observedIdentity.revision)
        : observedIdentity.revision;
  const normalizedTokens = useMemo(() => {
    return Array.from(
      new Set(tokens.map(normalizeToken).filter(isValidFileToken)),
    ).sort();
  }, [tokens]);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const statuses = statusesFor(
      workspaceKey,
      effectiveGeneration,
      effectiveRevision,
    );
    const unresolved = normalizedTokens.filter((token) => {
      const requestKey = pendingRequestKey(
        workspaceKey,
        effectiveGeneration,
        effectiveRevision,
        token,
      );
      return !statuses.has(token) && !pendingTokenRequests.has(requestKey);
    });
    if (unresolved.length === 0) return;

    const controllers = new Map<string, AbortController>();
    const timer = window.setTimeout(() => {
      for (const token of unresolved) {
        const controller = new AbortController();
        const requestKey = pendingRequestKey(
          workspaceKey,
          effectiveGeneration,
          effectiveRevision,
          token,
        );
        controllers.set(token, controller);
        pendingTokenRequests.add(requestKey);
        void searchFileMentions(token, 8, {
          exact: true,
          signal: controller.signal,
        })
          .then((result) => {
            if (controller.signal.aborted) return;
            const responseStatuses = statusesForResponse(
              workspaceKey,
              result.index_generation,
              result.index_revision,
            );
            if (result.items.some((item) => item.path === token)) {
              responseStatuses.set(token, "known");
            } else if (result.scan_status !== "scanning") {
              responseStatuses.set(token, "unknown");
            }
            setObservedIndex((current) => ({
              workspaceKey,
              sourceGeneration: optionGeneration,
              generation: result.index_generation,
              revision:
                current?.workspaceKey === workspaceKey
                && current.sourceGeneration === optionGeneration
                && current.generation === result.index_generation
                && current.revision !== null
                  ? Math.max(current.revision, result.index_revision)
                  : result.index_revision,
            }));
          })
          .catch((error: unknown) => {
            if (error instanceof DOMException && error.name === "AbortError") {
              return;
            }
            if (!controller.signal.aborted) {
              statuses.set(token, "unknown");
            }
          })
          .finally(() => {
            pendingTokenRequests.delete(requestKey);
            controllers.delete(token);
            setVersion((current) => current + 1);
          });
      }
    }, FILE_EXISTENCE_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      for (const [token, controller] of controllers) {
        controller.abort();
        pendingTokenRequests.delete(
          pendingRequestKey(
            workspaceKey,
            effectiveGeneration,
            effectiveRevision,
            token,
          ),
        );
      }
    };
  }, [
    effectiveGeneration,
    effectiveRevision,
    normalizedTokens,
    optionGeneration,
    version,
    workspaceKey,
  ]);

  void version;
  const isFileKnown = useCallback(
    (token: string) => {
      return (
        statusesFor(
          workspaceKey,
          effectiveGeneration,
          effectiveRevision,
        ).get(
          normalizeToken(token),
        ) === "known"
      );
    },
    [effectiveGeneration, effectiveRevision, workspaceKey],
  );

  return {
    isFileKnown,
    statuses: new Map(
      statusesFor(workspaceKey, effectiveGeneration, effectiveRevision),
    ),
  };
}

export function resetFileExistenceForTest(): void {
  fileExistenceCache.clear();
  pendingTokenRequests.clear();
}