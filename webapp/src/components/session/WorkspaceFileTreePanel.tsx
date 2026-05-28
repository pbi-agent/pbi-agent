import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDownIcon,
  ChevronRightIcon,
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
  workspaceFileDiffQueryKey,
  workspaceFilePreviewQueryKey,
  workspaceFileTreeQueryKey,
} from "./workspaceFileTreeQueries";
import { GitDiffResult } from "./GitDiffResult";
import { MarkdownContent } from "../shared/MarkdownContent";
import { Alert, AlertDescription } from "../ui/alert";
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
  const [searchTerm, setSearchTerm] = useState("");
  const [showChangedOnly, setShowChangedOnly] = useState(false);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(() => new Set());
  const [collapsedChangedPaths, setCollapsedChangedPaths] = useState<Set<string>>(() => new Set());
  const treeQueryKey = workspaceFileTreeQueryKey(workspaceKey);
  const treeQuery = useQuery({
    queryKey: treeQueryKey,
    queryFn: fetchWorkspaceFileTree,
    refetchInterval: 2000,
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
        '.workspace-tree__row--file[data-selected="true"]',
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
      className="workspace-file-panel"
      aria-label="Workspace file tree"
    >
      <header className="workspace-file-panel__header">
        <div className="workspace-file-panel__heading">
          <h2>Files</h2>
          <p>
            {treeQuery.data?.file_count ?? 0} files
            {treeQuery.data?.truncated ? " · truncated" : ""}
            {treeQuery.data?.is_stale ? " · refreshing" : ""}
          </p>
        </div>
        <SidebarSearchField
          className="workspace-file-panel__header-search"
          value={searchTerm}
          onChange={setSearchTerm}
          placeholder="Search files"
          ariaLabel="Search files"
        />
        <div className="workspace-file-panel__filters">
          <Toggle
            type="button"
            pressed={effectiveShowChangedOnly}
            onPressedChange={(pressed) => {
              setShowChangedOnly(pressed);
              setCollapsedChangedPaths(new Set());
            }}
            disabled={gitStatusFilterDisabled}
            className="workspace-file-panel__changed-toggle"
            aria-label={`Show changed files only (${changedFileCount} changed)`}
            title={
              gitStatusFilterDisabled
                ? "Git status is unavailable for this workspace"
                : "Show only files with git changes"
            }
          >
            <span>Changed</span>
            <span className="workspace-file-panel__changed-count">{changedFileCount}</span>
          </Toggle>
        </div>
        <div className="workspace-file-panel__actions">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="workspace-file-panel__close app-close-icon-button"
            aria-label="Close file tree panel"
            onClick={onClose}
          >
            <XIcon aria-hidden="true" />
          </Button>
        </div>
      </header>
      {treeQuery.error || treeQuery.data?.error ? (
        <Alert variant="destructive" className="workspace-file-panel__alert">
          <AlertDescription>
            {treeQuery.data?.error
              ?? treeQuery.error?.message
              ?? "Unable to load file tree."}
          </AlertDescription>
        </Alert>
      ) : null}
      <ResizablePanelGroup
        direction="vertical"
        className="workspace-file-panel__body"
      >
        <ResizablePanel
          id="workspace-file-tree-list"
          defaultSize={
            selectedPath === null
              ? "100%"
              : `${TREE_WITH_PREVIEW_DEFAULT_PERCENT}%`
          }
          minSize="10rem"
          className="workspace-file-panel__tree-panel"
        >
          <div className="workspace-file-panel__tree" ref={treeContainerRef}>
            <ScrollArea className="workspace-file-panel__tree-scroll" type="auto">
              {treeQuery.isPending || showInitialScan ? (
                <div className="workspace-file-panel__skeleton" aria-label="Loading files">
                  <Skeleton />
                  <Skeleton />
                  <Skeleton />
                </div>
              ) : tree.length === 0 ? (
                <p className="workspace-file-panel__empty">No files found.</p>
              ) : visibleTree.length === 0 ? (
                <p className="workspace-file-panel__empty">{visibleEmptyMessage}</p>
              ) : (
                <ul className="workspace-tree" role="tree" aria-label="Workspace files">
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
              className="workspace-file-panel__preview-panel"
            >
              <section className="workspace-file-panel__preview" aria-label="File preview">
                <div className="workspace-file-panel__preview-heading">
                  <span>{selectedPath}</span>
                  <div className="workspace-file-panel__preview-actions">
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
                        className="workspace-file-panel__preview-mode-toggle"
                        aria-label="Preview mode"
                      >
                        <ToggleGroupItem
                          value="diff"
                          className="workspace-file-panel__preview-mode-option"
                        >
                          Diff
                        </ToggleGroupItem>
                        <ToggleGroupItem
                          value="raw"
                          className="workspace-file-panel__preview-mode-option"
                        >
                          Raw
                        </ToggleGroupItem>
                      </ToggleGroup>
                    ) : null}
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      className="workspace-file-panel__preview-close app-close-icon-button"
                      aria-label="Close file preview"
                      onClick={() => setSelectedPath(null)}
                    >
                      <XIcon aria-hidden="true" />
                    </Button>
                  </div>
                </div>
                {activePreviewMode === "diff" && selectedCanDiff ? (
                  diffQuery.isPending ? (
                    <div className="workspace-file-panel__skeleton" aria-label="Loading diff">
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
                    <GitDiffResult
                      metadata={{
                        tool_name: "apply_patch",
                        path: selectedPath,
                        diff: diffQuery.data?.diff ?? "",
                        operation: operationForStatus(selectedGitStatus),
                        success: true,
                      }}
                    />
                  )
                ) : previewQuery.isPending ? (
                  <div className="workspace-file-panel__skeleton" aria-label="Loading preview">
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
      <div className="workspace-file-panel__markdown timeline-entry timeline-entry--assistant">
        <div className="timeline-entry__content workspace-file-panel__markdown-content">
          <MarkdownContent content={content} copyable />
        </div>
      </div>
    );
  }

  return (
    <CodeBlock
      value={content}
      path={path}
      className="workspace-file-panel__code"
    />
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
          className="workspace-tree__row workspace-tree__row--file"
          data-selected={node.path === selectedPath ? "true" : undefined}
          data-git-status={node.item.git_status ?? undefined}
          title={node.path}
          onClick={() => onSelect(node.path, node.item?.git_status ?? null)}
        >
          <span className="workspace-tree__chevron" aria-hidden="true" />
          <WorkspaceIcon icon={icon} />
          <span
            className="workspace-tree__name"
            data-git-status={node.item.git_status ?? undefined}
          >
            {node.name}
          </span>
          {node.item.git_status ? (
            <span
              className="workspace-tree__git-marker workspace-tree__status"
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
        className="workspace-tree__row workspace-tree__row--folder"
        title={node.path}
        onClick={() => onToggle(node.path)}
      >
        <span className="workspace-tree__chevron" aria-hidden="true">
          {expanded ? <ChevronDownIcon /> : <ChevronRightIcon />}
        </span>
        <WorkspaceIcon icon={icon} />
        <span className="workspace-tree__name">{node.name}</span>
        {node.hasGitStatus ? (
          <span
            className="workspace-tree__git-marker workspace-tree__folder-dot"
            aria-label="Contains git changes"
          />
        ) : null}
      </button>
      {expanded && node.children.length > 0 ? (
        <ul className="workspace-tree__group" role="group">
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

function WorkspaceIcon({ icon }: { icon: WorkspaceTreeIcon }) {
  return (
    <img
      className="workspace-tree__icon"
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