export const WORKSPACE_FILE_TREE_REFETCH_INTERVAL_MS = 2000;
export const WORKSPACE_FILE_TREE_STALE_TIME_MS = 2000;

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
