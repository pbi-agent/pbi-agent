export const WORKSPACE_FILE_TREE_REFETCH_INTERVAL_MS = 2000;
export const WORKSPACE_FILE_TREE_STALE_TIME_MS = 2000;
// Slow poll used only for the closed-explorer change badge; the open panel
// owns the fast poll so the two observers never double up.
export const WORKSPACE_FILE_TREE_SUMMARY_REFETCH_INTERVAL_MS = 15_000;

export function workspaceFileTreeQueryKey(workspaceKey: string | null | undefined) {
  return ["workspace-file-tree", workspaceKey ?? null] as const;
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
