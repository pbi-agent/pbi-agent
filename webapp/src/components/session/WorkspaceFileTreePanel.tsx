import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDownIcon,
  ChevronRightIcon,
  Columns2Icon,
  Rows2Icon,
  XIcon,
} from "lucide-react";
import {
  fetchWorkspaceFileDiff,
  fetchWorkspaceFilePreview,
  fetchWorkspaceFileTree,
} from "../../api";
import type { GitFileStatus, WorkspaceFileTreeItem } from "../../types";
import {
  getWorkspaceFileIcon,
  getWorkspaceFolderIcon,
  type WorkspaceTreeIcon,
} from "../../lib/workspaceFileIcons";
import {
  WORKSPACE_FILE_TREE_STALE_TIME_MS,
  workspaceFileDiffQueryKey,
  workspaceFilePreviewQueryKey,
  workspaceFileTreeQueryKey,
} from "./workspaceFileTreeQueries";
import { GitDiffResult, type GitDiffLayout } from "./GitDiffResult";
import { MarkdownContent } from "../shared/MarkdownContent";
import { cn } from "../../lib/utils";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { CodeBlock } from "../ui/code-block";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../ui/resizable";
import { ScrollArea } from "../ui/scroll-area";
import { Skeleton } from "../ui/skeleton";
import { Toggle } from "../ui/toggle";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";
import { SidebarSearchField } from "./SidebarSearchField";

type TreeNode = {
  name: string;
  path: string;
  children: TreeNode[];
  item: WorkspaceFileTreeItem | null;
  hasGitStatus: boolean;
};

type PreviewMode = "diff" | "raw";

const PREVIEW_AUTO_MAX_PERCENT = 72;
const TREE_WITH_PREVIEW_DEFAULT_PERCENT = 100 - PREVIEW_AUTO_MAX_PERCENT;

export function WorkspaceFileTreePanel({
  workspaceKey,
  onClose,
}: {
  workspaceKey: string | null | undefined;
  onClose: () => void;
}) {
  const treeContainerRef = useRef<HTMLDivElement | null>(null);
  const selectedTreeScrollFrameRef = useRef<number | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedPathRevision, setSelectedPathRevision] = useState(0);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("raw");
  const [diffLayout, setDiffLayout] = useState<GitDiffLayout>("split");
  const [searchTerm, setSearchTerm] = useState("");
  const [showChangedOnly, setShowChangedOnly] = useState(false);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(() => new Set());
  const [collapsedChangedPaths, setCollapsedChangedPaths] = useState<Set<string>>(() => new Set());
  const treeQueryKey = workspaceFileTreeQueryKey(workspaceKey);
  const treeQuery = useQuery({
    queryKey: treeQueryKey,
    queryFn: fetchWorkspaceFileTree,
    // Polling is owned by SessionPage (workspaceFileTreeRefetchInterval).
    staleTime: WORKSPACE_FILE_TREE_STALE_TIME_MS,
  });
  const items = useMemo(
    () => treeQuery.data?.items ?? [],
    [treeQuery.data?.items],
  );
  const changedFileCount = useMemo(
    () => items.filter((item) => item.git_status != null).length,
    [items],
  );
  const selectedItem = useMemo(
    () => items.find((item) => item.path === selectedPath) ?? null,
    [items, selectedPath],
  );
  const selectedGitStatus = selectedItem?.git_status ?? null;
  const selectedCanPreviewRaw = selectedGitStatus !== "D";
  const selectedCanDiff = selectedGitStatus !== null;
  const activePreviewMode = selectedCanDiff
    ? (selectedCanPreviewRaw ? previewMode : "diff")
    : "raw";
  const previewQuery = useQuery({
    queryKey: workspaceFilePreviewQueryKey(workspaceKey, selectedPath),
    queryFn: () => fetchWorkspaceFilePreview(selectedPath!),
    enabled: selectedPath !== null && activePreviewMode === "raw",
  });
  const gitStatusVersion = treeQuery.data?.git_status_version ?? null;
  const diffQuery = useQuery({
    queryKey: workspaceFileDiffQueryKey(workspaceKey, selectedPath, gitStatusVersion),
    queryFn: () => fetchWorkspaceFileDiff(selectedPath!),
    enabled: selectedPath !== null && activePreviewMode === "diff" && selectedCanDiff,
  });
  const tree = useMemo(
    () => buildTree(items),
    [items],
  );
  const normalizedSearch = searchTerm.trim().toLowerCase();
  const gitStatusFilterDisabled = treeQuery.data != null && treeQuery.data.git_repository === false;
  const effectiveShowChangedOnly = showChangedOnly && !gitStatusFilterDisabled;
  const filteredByGitStatusTree = useMemo(
    () => (effectiveShowChangedOnly ? filterChangedTree(tree) : tree),
    [effectiveShowChangedOnly, tree],
  );
  const changedFolderPaths = useMemo(
    () => collectFolderPaths(filteredByGitStatusTree),
    [filteredByGitStatusTree],
  );
  const changedFolderPathSet = useMemo(
    () => new Set(changedFolderPaths),
    [changedFolderPaths],
  );
  const displayedExpandedPaths = useMemo(() => {
    const paths = new Set(expandedPaths);
    if (!effectiveShowChangedOnly) return paths;
    for (const path of collapsedChangedPaths) {
      paths.delete(path);
    }
    for (const path of changedFolderPaths) {
      if (!collapsedChangedPaths.has(path)) {
        paths.add(path);
      }
    }
    return paths;
  }, [
    changedFolderPaths,
    collapsedChangedPaths,
    effectiveShowChangedOnly,
    expandedPaths,
  ]);
  const visibleTree = useMemo(
    () => filterTree(filteredByGitStatusTree, normalizedSearch),
    [filteredByGitStatusTree, normalizedSearch],
  );
  const visibleEmptyMessage = effectiveShowChangedOnly
    ? normalizedSearch.length > 0
      ? "No matching changed files."
      : "No changed files."
    : "No matching files.";
  const scanStillRunning =
    treeQuery.data?.scan_status === "scanning" || treeQuery.data?.is_stale === true;
  const showInitialScan =
    (treeQuery.data?.scan_status === "scanning" || treeQuery.data?.is_stale === true)
    && tree.length === 0;
  const scheduleSelectedTreeRowScroll = useCallback(() => {
    if (selectedTreeScrollFrameRef.current !== null) {
      cancelTreeScrollFrame(selectedTreeScrollFrameRef.current);
    }
    selectedTreeScrollFrameRef.current = requestTreeScrollFrame(() => {
      selectedTreeScrollFrameRef.current = null;
      const selectedRow = treeContainerRef.current?.querySelector<HTMLElement>(
        '[data-tree-row="file"][data-selected="true"]',
      );
      selectedRow?.scrollIntoView?.({ block: "start", inline: "nearest" });
    });
  }, []);

  useEffect(() => {
    if (!scanStillRunning || treeQuery.isFetching) return undefined;
    const timeoutId = window.setTimeout(() => {
      void treeQuery.refetch();
    }, 1000);
    return () => window.clearTimeout(timeoutId);
  }, [scanStillRunning, treeQuery]);

  useEffect(() => () => {
    if (selectedTreeScrollFrameRef.current !== null) {
      cancelTreeScrollFrame(selectedTreeScrollFrameRef.current);
    }
  }, []);

  useLayoutEffect(() => {
    if (selectedPath === null) return;
    scheduleSelectedTreeRowScroll();
  }, [
    scheduleSelectedTreeRowScroll,
    selectedPath,
    selectedPathRevision,
  ]);

  const togglePath = (path: string) => {
    const isExpanded = displayedExpandedPaths.has(path);
    if (effectiveShowChangedOnly && changedFolderPathSet.has(path)) {
      setCollapsedChangedPaths((current) => {
        const next = new Set(current);
        if (isExpanded) {
          next.add(path);
        } else {
          next.delete(path);
        }
        return next;
      });
      setExpandedPaths((current) => {
        const next = new Set(current);
        if (isExpanded) {
          next.delete(path);
        } else {
          next.add(path);
        }
        return next;
      });
      return;
    }
    setExpandedPaths((current) => {
      const next = new Set(current);
      if (isExpanded) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  return (
    <aside
      id="workspace-file-tree-panel"
      className="flex size-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background"
      aria-label="Workspace explorer"
    >
      <header data-panel-header="" className="flex min-h-12 shrink-0 flex-wrap items-center gap-3 border-b border-border bg-sidebar px-3 py-2">
        <div className="flex min-w-0 shrink-0 flex-col">
          <h2 className="truncate text-sm font-semibold">Files</h2>
          <p className="truncate text-xs text-muted-foreground">
            {treeQuery.data?.file_count ?? 0} files
            {treeQuery.data?.truncated ? " · truncated" : ""}
            {treeQuery.data?.is_stale ? " · refreshing" : ""}
          </p>
        </div>
        <SidebarSearchField
          className="min-w-0 flex-1 basis-64"
          value={searchTerm}
          onChange={setSearchTerm}
          placeholder="Search files"
          ariaLabel="Search files"
          clearLabel="Clear file search"
        />
        <div className="flex shrink-0 items-center">
          <Toggle
            type="button"
            pressed={effectiveShowChangedOnly}
            onPressedChange={(pressed) => {
              setShowChangedOnly(pressed);
              setCollapsedChangedPaths(new Set());
            }}
            disabled={gitStatusFilterDisabled}
            variant="outline"
            size="sm"
            aria-label={`Show changed files only (${changedFileCount} changed)`}
            title={
              gitStatusFilterDisabled
                ? "Git status is unavailable for this workspace"
                : "Show only files with git changes"
            }
          >
            <span>Changed</span>
            <Badge variant="secondary">{changedFileCount}</Badge>
          </Toggle>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Close workspace explorer panel"
            onClick={onClose}
          >
            <XIcon aria-hidden="true" />
          </Button>
        </div>
      </header>
      {treeQuery.error || treeQuery.data?.error ? (
        <div className="shrink-0 p-3">
          <Alert variant="destructive">
            <AlertDescription>
              {treeQuery.data?.error
                ?? treeQuery.error?.message
                ?? "Unable to load file tree."}
            </AlertDescription>
          </Alert>
        </div>
      ) : null}
      <ResizablePanelGroup
        direction="vertical"
        className="min-h-0 flex-1"
      >
        <ResizablePanel
          id="workspace-file-tree-list"
          defaultSize={
            selectedPath === null
              ? "100%"
              : `${TREE_WITH_PREVIEW_DEFAULT_PERCENT}%`
          }
          minSize="10rem"
          className="flex min-h-0 flex-col"
        >
          <div className="flex size-full min-h-0 flex-col overflow-hidden" ref={treeContainerRef}>
            <ScrollArea className="min-h-0 flex-1" type="auto">
              {treeQuery.isPending || showInitialScan ? (
                <div className="flex flex-col gap-2 p-3" aria-label="Loading files">
                  <Skeleton />
                  <Skeleton />
                  <Skeleton />
                </div>
              ) : tree.length === 0 ? (
                <p className="p-3 text-sm text-muted-foreground">No files found.</p>
              ) : visibleTree.length === 0 ? (
                <p className="p-3 text-sm text-muted-foreground">{visibleEmptyMessage}</p>
              ) : (
                <ul className="flex flex-col p-2" role="tree" aria-label="Workspace files">
                  {visibleTree.map((node) => (
                    <TreeNodeView
                      key={node.path}
                      node={node}
                      selectedPath={selectedPath}
                      expandedPaths={displayedExpandedPaths}
                      forceExpanded={normalizedSearch.length > 0}
                      onToggle={togglePath}
                      onSelect={(path, gitStatus) => {
                        setSelectedPath(path);
                        setSelectedPathRevision((revision) => revision + 1);
                        setPreviewMode(gitStatus === null ? "raw" : "diff");
                      }}
                    />
                  ))}
                </ul>
              )}
            </ScrollArea>
          </div>
        </ResizablePanel>
        {selectedPath !== null ? (
          <>
            <ResizableHandle
              direction="vertical"
              aria-label="Resize file tree and preview"
              withHandle
            />
            <ResizablePanel
              id="workspace-file-preview"
              defaultSize={`${PREVIEW_AUTO_MAX_PERCENT}%`}
              minSize="8rem"
              className="flex min-h-0 flex-col"
            >
              <section className="flex size-full min-h-0 min-w-0 flex-col gap-2 overflow-hidden p-3" aria-label="File preview">
                <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 font-mono text-xs break-all text-muted-foreground">
                  <span>{selectedPath}</span>
                  <div className="flex shrink-0 items-center gap-2">
                    {selectedCanDiff && selectedCanPreviewRaw ? (
                      <ToggleGroup
                        type="single"
                        value={activePreviewMode}
                        onValueChange={(value) => {
                          if (value === "diff" || value === "raw") {
                            setPreviewMode(value);
                          }
                        }}
                        variant="outline"
                        size="sm"
                        aria-label="Preview mode"
                      >
                        <ToggleGroupItem
                          value="diff"
                        >
                          Diff
                        </ToggleGroupItem>
                        <ToggleGroupItem
                          value="raw"
                        >
                          Raw
                        </ToggleGroupItem>
                      </ToggleGroup>
                    ) : null}
                    {activePreviewMode === "diff" && selectedCanDiff ? (
                      <ToggleGroup
                        type="single"
                        value={diffLayout}
                        onValueChange={(value) => {
                          if (value === "split" || value === "stacked") {
                            setDiffLayout(value);
                          }
                        }}
                        variant="outline"
                        size="sm"
                        aria-label="Diff layout"
                      >
                        <ToggleGroupItem
                          value="split"
                        >
                          <Columns2Icon data-icon="inline-start" aria-hidden="true" />
                          Split
                        </ToggleGroupItem>
                        <ToggleGroupItem
                          value="stacked"
                        >
                          <Rows2Icon data-icon="inline-start" aria-hidden="true" />
                          Stacked
                        </ToggleGroupItem>
                      </ToggleGroup>
                    ) : null}
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Close file preview"
                      onClick={() => setSelectedPath(null)}
                    >
                      <XIcon aria-hidden="true" />
                    </Button>
                  </div>
                </div>
                {activePreviewMode === "diff" && selectedCanDiff ? (
                  diffQuery.isPending ? (
                    <div className="flex flex-col gap-2" aria-label="Loading diff">
                      <Skeleton />
                      <Skeleton />
                    </div>
                  ) : diffQuery.error ? (
                    <Alert variant="destructive">
                      <AlertDescription>{diffQuery.error.message}</AlertDescription>
                    </Alert>
                  ) : diffQuery.data?.error ? (
                    <DiffErrorMessage error={diffQuery.data.error} />
                  ) : (
                    <div className="flex min-h-0 flex-1 flex-col *:min-h-0 *:flex-1">
                    <GitDiffResult
                      metadata={{
                        tool_name: "apply_patch",
                        path: selectedPath,
                        diff: diffQuery.data?.diff ?? "",
                        operation: operationForStatus(selectedGitStatus),
                        success: true,
                      }}
                      layout={diffLayout}
                    />
                    </div>
                  )
                ) : previewQuery.isPending ? (
                  <div className="flex flex-col gap-2" aria-label="Loading preview">
                    <Skeleton />
                    <Skeleton />
                  </div>
                ) : previewQuery.error ? (
                  <Alert variant="destructive">
                    <AlertDescription>{previewQuery.error.message}</AlertDescription>
                  </Alert>
                ) : previewQuery.data?.error ? (
                  <PreviewErrorMessage error={previewQuery.data.error} />
                ) : (
                  <FilePreviewContent
                    content={previewQuery.data?.content ?? ""}
                    path={selectedPath}
                  />
                )}
              </section>
            </ResizablePanel>
          </>
        ) : null}
      </ResizablePanelGroup>
    </aside>
  );
}

function FilePreviewContent({
  content,
  path,
}: {
  content: string;
  path: string;
}) {
  if (isMarkdownPath(path)) {
    return (
      <div className="min-h-0 w-full min-w-0 flex-1 overflow-auto">
        <div className="min-h-full rounded-md border border-border bg-card p-4 text-sm leading-relaxed">
          <MarkdownContent content={content} copyable />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-auto">
      <CodeBlock value={content} path={path} />
    </div>
  );
}

function isMarkdownPath(path: string): boolean {
  const normalizedPath = path.toLowerCase();
  return normalizedPath.endsWith(".md") || normalizedPath.endsWith(".markdown");
}

function TreeNodeView({
  node,
  selectedPath,
  expandedPaths,
  forceExpanded,
  onToggle,
  onSelect,
}: {
  node: TreeNode;
  selectedPath: string | null;
  expandedPaths: Set<string>;
  forceExpanded: boolean;
  onToggle: (path: string) => void;
  onSelect: (path: string, gitStatus: GitFileStatus | null) => void;
}) {
  if (node.item) {
    const icon = getWorkspaceFileIcon(
      node.path,
      node.item.kind === "image" ? "image" : undefined,
    );
    return (
      <li role="treeitem" aria-selected={node.path === selectedPath}>
        <button
          type="button"
          data-tree-row="file"
          className={TREE_ROW_CLASS_NAME}
          data-selected={node.path === selectedPath ? "true" : undefined}
          data-git-status={node.item.git_status ?? undefined}
          title={node.path}
          onClick={() => onSelect(node.path, node.item?.git_status ?? null)}
        >
          <span className="inline-flex size-4 shrink-0" aria-hidden="true" />
          <WorkspaceIcon icon={icon} />
          <span
            className={cn("min-w-0 flex-1 truncate", node.item.git_status && GIT_STATUS_CLASS_NAME[node.item.git_status])}
            data-git-status={node.item.git_status ?? undefined}
          >
            {node.name}
          </span>
          {node.item.git_status ? (
            <span
              data-git-marker="status"
              className={cn("shrink-0 font-mono text-xs font-semibold", GIT_STATUS_CLASS_NAME[node.item.git_status])}
              data-status={node.item.git_status}
              aria-label={`Git status ${node.item.git_status}`}
            >
              {node.item.git_status}
            </span>
          ) : null}
        </button>
      </li>
    );
  }
  const expanded = forceExpanded || expandedPaths.has(node.path);
  const icon = getWorkspaceFolderIcon(node.path, expanded);
  return (
    <li role="treeitem" aria-expanded={expanded}>
      <button
        type="button"
        data-tree-row="folder"
        className={TREE_ROW_CLASS_NAME}
        title={node.path}
        onClick={() => onToggle(node.path)}
      >
        <span className="inline-flex size-4 shrink-0 items-center justify-center text-muted-foreground" aria-hidden="true">
          {expanded ? <ChevronDownIcon /> : <ChevronRightIcon />}
        </span>
        <WorkspaceIcon icon={icon} />
        <span className="min-w-0 flex-1 truncate">{node.name}</span>
        {node.hasGitStatus ? (
          <span
            data-git-marker="folder"
            className="size-1.5 shrink-0 rounded-full bg-primary"
            aria-label="Contains git changes"
          />
        ) : null}
      </button>
      {expanded && node.children.length > 0 ? (
        <ul className="ml-3 flex flex-col border-l border-border pl-1" role="group">
          {node.children.map((child) => (
            <TreeNodeView
              key={child.path}
              node={child}
              selectedPath={selectedPath}
              expandedPaths={expandedPaths}
              forceExpanded={forceExpanded}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

const TREE_ROW_CLASS_NAME =
  "flex w-full min-w-0 items-center gap-1.5 rounded-sm px-2 py-1 text-left text-sm text-foreground outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring data-[selected=true]:bg-primary/10 data-[selected=true]:text-primary";

const GIT_STATUS_CLASS_NAME: Partial<Record<GitFileStatus, string>> = {
  M: "text-primary",
  D: "text-destructive",
  U: "text-destructive",
};

function WorkspaceIcon({ icon }: { icon: WorkspaceTreeIcon }) {
  return (
    <img
      className="size-4 shrink-0"
      src={icon.url}
      alt=""
      aria-hidden="true"
      draggable={false}
      data-icon-name={icon.iconName}
    />
  );
}

function PreviewErrorMessage({
  error,
}: {
  error: "not_found" | "binary" | "too_large" | "outside_workspace" | "read_failed";
}) {
  const message = {
    not_found: "File not found.",
    binary: "Binary files cannot be previewed.",
    too_large: "This file is too large to preview.",
    outside_workspace: "File is outside the workspace.",
    read_failed: "Unable to read this file.",
  }[error];
  return (
    <Alert>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}

function DiffErrorMessage({
  error,
}: {
  error: "not_git_repository" | "not_found" | "binary" | "outside_workspace" | "git_failed";
}) {
  const message = {
    not_git_repository: "This workspace is not a git repository.",
    not_found: "No git diff is available for this file.",
    binary: "Binary file diffs cannot be previewed.",
    outside_workspace: "File is outside the workspace.",
    git_failed: "Unable to read git diff for this file.",
  }[error];
  return (
    <Alert>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}

function operationForStatus(status: GitFileStatus | null): string {
  if (status === "A" || status === "?") return "create_file";
  if (status === "R") return "move_file";
  return "update_file";
}

export function getAutoPreviewPanelSize(
  _content: string,
  panelBodyHeightPx: number,
): string | null {
  if (!Number.isFinite(panelBodyHeightPx) || panelBodyHeightPx <= 0) return null;
  return `${PREVIEW_AUTO_MAX_PERCENT}%`;
}

function requestTreeScrollFrame(callback: FrameRequestCallback): number {
  if (typeof window.requestAnimationFrame === "function") {
    return window.requestAnimationFrame(callback);
  }
  return window.setTimeout(() => callback(window.performance.now()), 0);
}

function cancelTreeScrollFrame(frameId: number): void {
  if (typeof window.cancelAnimationFrame === "function") {
    window.cancelAnimationFrame(frameId);
    return;
  }
  window.clearTimeout(frameId);
}

function buildTree(items: WorkspaceFileTreeItem[]): TreeNode[] {
  const root: TreeNode = {
    name: "",
    path: "",
    children: [],
    item: null,
    hasGitStatus: false,
  };
  const directories = new Map<string, TreeNode>([["", root]]);
  for (const item of items) {
    const parts = item.path.split("/").filter(Boolean);
    let parent = root;
    let currentPath = "";
    for (const part of parts.slice(0, -1)) {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      let directory = directories.get(currentPath);
      if (!directory) {
        directory = {
          name: part,
          path: currentPath,
          children: [],
          item: null,
          hasGitStatus: false,
        };
        directories.set(currentPath, directory);
        parent.children.push(directory);
      }
      parent = directory;
    }
    const name = parts.at(-1);
    if (!name) continue;
    parent.children.push({
      name,
      path: item.path,
      children: [],
      item,
      hasGitStatus: item.git_status != null,
    });
  }
  updateFolderGitStatus(root);
  sortTree(root.children);
  return root.children;
}

function updateFolderGitStatus(node: TreeNode): boolean {
  if (node.item) return node.hasGitStatus;
  let hasChangedDescendant = false;
  for (const child of node.children) {
    hasChangedDescendant = updateFolderGitStatus(child) || hasChangedDescendant;
  }
  node.hasGitStatus = hasChangedDescendant;
  return node.hasGitStatus;
}

function filterTree(nodes: TreeNode[], query: string): TreeNode[] {
  if (!query) return nodes;
  return nodes.flatMap((node) => {
    const matches = nodeMatches(node, query);
    if (node.item) return matches ? [node] : [];
    const children = matches ? node.children : filterTree(node.children, query);
    if (!matches && children.length === 0) return [];
    return [{ ...node, children }];
  });
}

function filterChangedTree(nodes: TreeNode[]): TreeNode[] {
  return nodes.flatMap((node) => {
    if (node.item) return node.hasGitStatus ? [node] : [];
    if (!node.hasGitStatus) return [];
    return [{ ...node, children: filterChangedTree(node.children) }];
  });
}

function collectFolderPaths(nodes: TreeNode[]): string[] {
  const paths: string[] = [];
  for (const node of nodes) {
    if (node.item) continue;
    paths.push(node.path);
    paths.push(...collectFolderPaths(node.children));
  }
  return paths;
}

function nodeMatches(node: TreeNode, query: string): boolean {
  return (
    node.name.toLowerCase().includes(query)
    || node.path.toLowerCase().includes(query)
  );
}

function sortTree(nodes: TreeNode[]) {
  nodes.sort((left, right) => {
    if (left.item && !right.item) return 1;
    if (!left.item && right.item) return -1;
    return left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
  });
  for (const node of nodes) sortTree(node.children);
}