import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDownIcon,
  ChevronRightIcon,
  FileTextIcon,
  FolderIcon,
  ImageIcon,
  RefreshCwIcon,
  XIcon,
} from "lucide-react";
import {
  fetchWorkspaceFilePreview,
  fetchWorkspaceFileTree,
  refreshWorkspaceFileTree,
} from "../../api";
import type { FileMentionItem } from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { CodeBlock } from "../ui/code-block";
import { Input } from "../ui/input";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../ui/resizable";
import { ScrollArea } from "../ui/scroll-area";
import { Skeleton } from "../ui/skeleton";

type TreeNode = {
  name: string;
  path: string;
  children: TreeNode[];
  item: FileMentionItem | null;
};

export function workspaceFileTreeQueryKey(workspaceKey: string | null | undefined) {
  return ["workspace-file-tree", workspaceKey ?? null] as const;
}

export function workspaceFilePreviewQueryKey(
  workspaceKey: string | null | undefined,
  path: string | null,
) {
  return ["workspace-file-preview", workspaceKey ?? null, path] as const;
}

export function WorkspaceFileTreePanel({
  workspaceKey,
  onClose,
}: {
  workspaceKey: string | null | undefined;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(() => new Set());
  const treeQueryKey = workspaceFileTreeQueryKey(workspaceKey);
  const treeQuery = useQuery({
    queryKey: treeQueryKey,
    queryFn: fetchWorkspaceFileTree,
  });
  const refreshMutation = useMutation({
    mutationFn: refreshWorkspaceFileTree,
    onSuccess: (payload) => {
      queryClient.setQueryData(treeQueryKey, payload);
    },
  });
  const previewQuery = useQuery({
    queryKey: workspaceFilePreviewQueryKey(workspaceKey, selectedPath),
    queryFn: () => fetchWorkspaceFilePreview(selectedPath!),
    enabled: selectedPath !== null,
  });
  const items = useMemo(
    () => treeQuery.data?.items ?? [],
    [treeQuery.data?.items],
  );
  const tree = useMemo(
    () => buildTree(items),
    [items],
  );
  const normalizedSearch = searchTerm.trim().toLowerCase();
  const visibleTree = useMemo(
    () => filterTree(tree, normalizedSearch),
    [normalizedSearch, tree],
  );
  const isRefreshing = refreshMutation.isPending || treeQuery.isFetching;
  const scanStillRunning =
    treeQuery.data?.scan_status === "scanning" || treeQuery.data?.is_stale === true;
  const showInitialScan =
    (treeQuery.data?.scan_status === "scanning" || treeQuery.data?.is_stale === true)
    && tree.length === 0;

  useEffect(() => {
    if (!scanStillRunning || treeQuery.isFetching) return undefined;
    const timeoutId = window.setTimeout(() => {
      void treeQuery.refetch();
    }, 1000);
    return () => window.clearTimeout(timeoutId);
  }, [scanStillRunning, treeQuery]);

  const togglePath = (path: string) => {
    setExpandedPaths((current) => {
      const next = new Set(current);
      if (next.has(path)) {
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
        <div className="workspace-file-panel__actions">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="workspace-file-panel__action"
            aria-label="Refresh file tree"
            disabled={isRefreshing}
            onClick={() => {
              refreshMutation.mutate();
            }}
          >
            <RefreshCwIcon aria-hidden="true" />
          </Button>
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
      {treeQuery.error || refreshMutation.error || treeQuery.data?.error ? (
        <Alert variant="destructive" className="workspace-file-panel__alert">
          <AlertDescription>
            {treeQuery.data?.error
              ?? refreshMutation.error?.message
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
          defaultSize="64%"
          minSize="10rem"
          className="workspace-file-panel__tree-panel"
        >
          <div className="workspace-file-panel__tree">
            <div className="workspace-file-panel__search">
              <Input
                type="search"
                aria-label="Search files"
                placeholder="Search files..."
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
              />
            </div>
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
                <p className="workspace-file-panel__empty">No matching files.</p>
              ) : (
                <ul className="workspace-tree" role="tree" aria-label="Workspace files">
                  {visibleTree.map((node) => (
                    <TreeNodeView
                      key={node.path}
                      node={node}
                      selectedPath={selectedPath}
                      expandedPaths={expandedPaths}
                      forceExpanded={normalizedSearch.length > 0}
                      onToggle={togglePath}
                      onSelect={setSelectedPath}
                    />
                  ))}
                </ul>
              )}
            </ScrollArea>
          </div>
        </ResizablePanel>
        <ResizableHandle
          direction="vertical"
          aria-label="Resize file tree and preview"
          withHandle
        />
        <ResizablePanel
          id="workspace-file-preview"
          defaultSize="36%"
          minSize="8rem"
          className="workspace-file-panel__preview-panel"
        >
          <section className="workspace-file-panel__preview" aria-label="File preview">
            {selectedPath === null ? (
              <p className="workspace-file-panel__empty">Select a file to preview it.</p>
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
              <>
                <div className="workspace-file-panel__preview-heading">
                  {selectedPath}
                </div>
                <CodeBlock
                  value={previewQuery.data?.content ?? ""}
                  path={selectedPath}
                  className="workspace-file-panel__code"
                />
              </>
            )}
          </section>
        </ResizablePanel>
      </ResizablePanelGroup>
    </aside>
  );
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
  onSelect: (path: string) => void;
}) {
  if (node.item) {
    const Icon = node.item.kind === "image" ? ImageIcon : FileTextIcon;
    return (
      <li role="treeitem" aria-selected={node.path === selectedPath}>
        <button
          type="button"
          className="workspace-tree__row workspace-tree__row--file"
          data-selected={node.path === selectedPath ? "true" : undefined}
          title={node.path}
          onClick={() => onSelect(node.path)}
        >
          <span className="workspace-tree__chevron" aria-hidden="true" />
          <Icon aria-hidden="true" />
          <span>{node.name}</span>
        </button>
      </li>
    );
  }
  const expanded = forceExpanded || expandedPaths.has(node.path);
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
        <FolderIcon aria-hidden="true" />
        <span>{node.name}</span>
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

function buildTree(items: FileMentionItem[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", children: [], item: null };
  const directories = new Map<string, TreeNode>([["", root]]);
  for (const item of items) {
    const parts = item.path.split("/").filter(Boolean);
    let parent = root;
    let currentPath = "";
    for (const part of parts.slice(0, -1)) {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      let directory = directories.get(currentPath);
      if (!directory) {
        directory = { name: part, path: currentPath, children: [], item: null };
        directories.set(currentPath, directory);
        parent.children.push(directory);
      }
      parent = directory;
    }
    const name = parts.at(-1);
    if (!name) continue;
    parent.children.push({ name, path: item.path, children: [], item });
  }
  sortTree(root.children);
  return root.children;
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