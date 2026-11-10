export const WORKSPACE_FILE_TREE_STALE_TIME_MS = 2000;
// Poll rate while the explorer is open and the user is watching the tree.
export const WORKSPACE_FILE_TREE_OPEN_REFETCH_INTERVAL_MS = 2000;
// Poll rate while the explorer is closed. This query also feeds the
// changed-files badge and the composer's file-index revision, but agent edits
// refresh it immediately via tool-completion events (useLiveSessionEvents),
// so this poll only needs to catch changes made outside the agent (editor,
// git checkout, etc.), where a delay of a few seconds is acceptable.
export const WORKSPACE_FILE_TREE_CLOSED_REFETCH_INTERVAL_MS = 15_000;

export const WORKSPACE_FILE_TREE_QUERY_PREFIX = "workspace-file-tree";

/**
 * Single source of truth for the file-tree poll rate. Only SessionPage (which
 * is always mounted for a session) polls; WorkspaceFileTreePanel observes the
 * same query without its own interval so requests never double up.
 */
export function workspaceFileTreeRefetchInterval(explorerOpen: boolean): number {
  return explorerOpen
    ? WORKSPACE_FILE_TREE_OPEN_REFETCH_INTERVAL_MS
    : WORKSPACE_FILE_TREE_CLOSED_REFETCH_INTERVAL_MS;
}

export function workspaceFileTreeQueryKey(workspaceKey: string | null | undefined) {
  return [WORKSPACE_FILE_TREE_QUERY_PREFIX, workspaceKey ?? null] as const;
}

export function workspaceFilePreviewQueryKey(
  workspaceKey: string | null | undefined,
  path: string | null,
) {
  return ["workspace-file-preview", workspaceKey ?? null, path] as const;
}

export function workspaceFileDiffQueryKey(
  workspaceKey: string | null | undefined,
  path: string | null,
  gitStatusVersion: string | null | undefined,
) {
  return [
    "workspace-file-diff",
    workspaceKey ?? null,
    path,
    gitStatusVersion ?? null,
  ] as const;
}
