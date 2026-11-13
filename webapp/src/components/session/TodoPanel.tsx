import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ComponentProps,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";
import type { Components } from "react-markdown";
import {
  AlertTriangleIcon,
  CircleCheckIcon,
  CircleDotIcon,
  CircleIcon,
  CircleSlashIcon,
  ListTodoIcon,
  OctagonAlertIcon,
  XIcon,
  type LucideIcon,
} from "lucide-react";

import { fetchWorkspaceFilePreview } from "../../api";
import type { WorkspaceFilePreviewPayload } from "../../types";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "../shared/MarkdownContent";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "../ui/empty";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "../ui/tabs";
import { workspaceFilePreviewQueryKey } from "./workspaceFileTreeQueries";

// Re-read the open file so ticks made by the agent show up live.
export const TODO_PREVIEW_REFETCH_INTERVAL_MS = 3000;

const TODO_FILE_NAME = "todo.md";

/** Workspace-relative paths of every `TODO.md` file, root first. */
export function findTodoFilePaths(paths: readonly string[]): string[] {
  return paths
    .filter((path) => {
      const name = path.split("/").pop() ?? "";
      return name.toLowerCase() === TODO_FILE_NAME;
    })
    .sort((left, right) => {
      const depth = left.split("/").length - right.split("/").length;
      return depth !== 0 ? depth : left.localeCompare(right);
    });
}

export type TodoStatus = "done" | "pending" | "progress" | "blocked" | "dropped";

const STATUS_BY_MARKER: Record<string, TodoStatus> = {
  " ": "pending",
  x: "done",
  X: "done",
  ">": "progress",
  "!": "blocked",
  "-": "dropped",
};

const STATUS_META: Record<TodoStatus, { icon: LucideIcon; label: string; className: string }> = {
  done: { icon: CircleCheckIcon, label: "Done", className: "text-primary" },
  pending: { icon: CircleIcon, label: "Pending", className: "text-muted-foreground" },
  progress: { icon: CircleDotIcon, label: "In progress", className: "text-primary" },
  blocked: { icon: OctagonAlertIcon, label: "Blocked", className: "text-destructive" },
  dropped: { icon: CircleSlashIcon, label: "Dropped", className: "text-muted-foreground" },
};

export type TodoCounts = Record<TodoStatus, number> & { total: number };

const TODO_LINE_PATTERN = /^\s*(?:[-*+]|\d+[.)])\s+\[([ xX>!-])\]\s/;

export function countTodoItems(content: string): TodoCounts {
  const counts: TodoCounts = { done: 0, pending: 0, progress: 0, blocked: 0, dropped: 0, total: 0 };
  let inFence = false;
  for (const line of content.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const match = TODO_LINE_PATTERN.exec(line);
    if (!match) continue;
    counts[STATUS_BY_MARKER[match[1]]] += 1;
    counts.total += 1;
  }
  return counts;
}

type MdastNode = {
  type: string;
  value?: string;
  checked?: boolean | null;
  children?: MdastNode[];
  data?: { hProperties?: Record<string, unknown> };
};

const EXTENDED_MARKER_PATTERN = /^\[([>!-])\]\s+/;

function firstTextNode(node: MdastNode): MdastNode | null {
  const first = node.children?.[0];
  if (!first) return null;
  if (first.type === "text") return first;
  return first.type === "paragraph" ? firstTextNode(first) : null;
}

/**
 * Tags list items with `data-todo-status`. Handles GFM `[ ]`/`[x]` and the
 * `[>]`/`[!]`/`[-]` markers from the workspace TODO convention, and clears
 * `checked` so the default disabled checkbox is not rendered.
 */
function remarkTodoStatus() {
  return (tree: MdastNode) => {
    // Returns the statuses found in `node` and below, so each list item can
    // record which statuses its sub-items carry (for filtering).
    const visit = (node: MdastNode): Set<TodoStatus> => {
      let status: TodoStatus | null = null;
      if (node.type === "listItem") {
        if (typeof node.checked === "boolean") {
          status = node.checked ? "done" : "pending";
          node.checked = null;
        } else {
          const text = firstTextNode(node);
          const match = text?.value ? EXTENDED_MARKER_PATTERN.exec(text.value) : null;
          if (text?.value && match) {
            status = STATUS_BY_MARKER[match[1]];
            text.value = text.value.slice(match[0].length);
          }
        }
      }
      const below = new Set<TodoStatus>();
      for (const child of node.children ?? []) {
        for (const found of visit(child)) below.add(found);
      }
      if (node.type === "listItem") {
        const hProperties: Record<string, unknown> = { ...node.data?.hProperties };
        if (status) hProperties["data-todo-status"] = status;
        if (below.size > 0) hProperties["data-todo-nested"] = [...below].sort().join(" ");
        node.data = { ...node.data, hProperties };
      }
      if (status) below.add(status);
      return below;
    };
    visit(tree);
  };
}

const TODO_REMARK_PLUGINS = [remarkTodoStatus];

const TodoFilterContext = createContext<TodoStatus | null>(null);

function TodoListItem({
  status,
  nested,
  children,
}: {
  status: TodoStatus | undefined;
  nested: readonly string[];
  children: ReactNode;
}) {
  const filter = useContext(TodoFilterContext);
  const matches = filter === null || status === filter;
  // Keep a non-matching parent visible (dimmed) when a sub-item matches.
  if (!matches && (filter === null || !nested.includes(filter))) {
    return null;
  }
  const context = !matches ? "opacity-60" : null;
  if (!status) {
    return <li className={cn("mb-1 leading-relaxed last:mb-0", context)}>{children}</li>;
  }
  const { icon: Icon, label, className } = STATUS_META[status];
  return (
    <li
      data-todo-status={status}
      className={cn(
        "relative mb-1 list-none leading-relaxed last:mb-0",
        status === "done" && "text-muted-foreground",
        status === "dropped" && "text-muted-foreground line-through",
        context,
      )}
    >
      <Icon
        role="img"
        aria-label={label}
        className={cn("absolute top-1 -left-5 size-3.5", className)}
      />
      {children}
    </li>
  );
}

const TODO_MARKDOWN_COMPONENTS: Components = {
  li(props) {
    const data = props as { "data-todo-status"?: TodoStatus; "data-todo-nested"?: string };
    const nested = data["data-todo-nested"]?.split(" ") ?? [];
    return (
      <TodoListItem status={data["data-todo-status"]} nested={nested}>
        {props.children}
      </TodoListItem>
    );
  },
};

function previewErrorMessage(error: WorkspaceFilePreviewPayload["error"]): string {
  switch (error) {
    case "too_large":
      return "This file is too large to preview.";
    case "binary":
      return "This file is not valid UTF-8 text.";
    case "not_found":
      return "This file no longer exists.";
    default:
      return "This file could not be read.";
  }
}

type BadgeVariant = NonNullable<ComponentProps<typeof Badge>["variant"]>;

const FILTER_BADGES: { status: TodoStatus; variant: BadgeVariant; label: (counts: TodoCounts) => string }[] = [
  { status: "done", variant: "secondary", label: (c) => `${c.done}/${c.total - c.dropped} done` },
  { status: "progress", variant: "info", label: (c) => `${c.progress} in progress` },
  { status: "blocked", variant: "destructive", label: (c) => `${c.blocked} blocked` },
  { status: "pending", variant: "outline", label: (c) => `${c.pending} pending` },
  { status: "dropped", variant: "outline", label: (c) => `${c.dropped} dropped` },
];

function TodoCountBadges({
  counts,
  filter,
  onFilterChange,
}: {
  counts: TodoCounts;
  filter: TodoStatus | null;
  onFilterChange: (filter: TodoStatus | null) => void;
}) {
  if (counts.total === 0) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      data-todo-counts=""
      role="group"
      aria-label="Filter by status"
    >
      {FILTER_BADGES.filter(({ status }) => status === "done" || counts[status] > 0).map(
        ({ status, variant, label }) => {
          const active = filter === status;
          return (
            <Badge key={status} asChild variant={active ? "default" : variant}>
              <button
                type="button"
                className="cursor-pointer"
                aria-pressed={active}
                disabled={counts[status] === 0}
                title={active ? "Show all items" : `Show only ${STATUS_META[status].label.toLowerCase()} items`}
                onClick={() => onFilterChange(active ? null : status)}
              >
                {label(counts)}
              </button>
            </Badge>
          );
        },
      )}
    </div>
  );
}

function TodoFileView({ path, workspaceKey }: { path: string; workspaceKey: string | null }) {
  const previewQuery = useQuery({
    queryKey: workspaceFilePreviewQueryKey(workspaceKey, path),
    queryFn: () => fetchWorkspaceFilePreview(path),
    refetchInterval: TODO_PREVIEW_REFETCH_INTERVAL_MS,
  });
  const content = previewQuery.data?.content ?? null;
  const counts = useMemo(() => (content ? countTodoItems(content) : null), [content]);
  const [selectedFilter, setSelectedFilter] = useState<TodoStatus | null>(null);
  // Drop the filter once live edits leave no item with that status.
  const filter = selectedFilter && counts && counts[selectedFilter] > 0 ? selectedFilter : null;

  if (previewQuery.isPending) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
    );
  }
  if (previewQuery.isError || previewQuery.data?.error) {
    return (
      <Alert variant="destructive">
        <AlertTriangleIcon />
        <AlertDescription>{previewErrorMessage(previewQuery.data?.error ?? null)}</AlertDescription>
      </Alert>
    );
  }
  if (!content?.trim()) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>Empty file</EmptyTitle>
          <EmptyDescription>{`${path} has no content yet.`}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {counts ? (
        <TodoCountBadges counts={counts} filter={filter} onFilterChange={setSelectedFilter} />
      ) : null}
      <div className="min-w-0 text-sm" data-todo-content="">
        <TodoFilterContext.Provider value={filter}>
          <MarkdownContent
            content={content}
            remarkPlugins={TODO_REMARK_PLUGINS}
            components={TODO_MARKDOWN_COMPONENTS}
          />
        </TodoFilterContext.Provider>
      </div>
    </div>
  );
}

export function TodoPanel({
  paths,
  workspaceKey,
  onClose,
}: {
  paths: readonly string[];
  workspaceKey: string | null;
  onClose?: () => void;
}) {
  const [selectedPath, setSelectedPath] = useState<string | null>(paths[0] ?? null);
  const activePath = selectedPath && paths.includes(selectedPath) ? selectedPath : paths[0] ?? null;

  return (
    <aside
      id="todo-panel"
      className="flex size-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background"
      aria-label="TODO"
    >
      <header
        data-panel-header=""
        className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border bg-sidebar px-3"
      >
        <div className="flex min-w-0 flex-col">
          <h2 className="truncate text-sm font-semibold">TODO</h2>
          <p className="truncate text-xs text-muted-foreground">
            {activePath ?? "No TODO.md file in this workspace"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Close TODO panel"
            onClick={onClose}
          >
            <XIcon aria-hidden="true" />
          </Button>
        </div>
      </header>
      {paths.length > 1 ? (
        <div className="flex shrink-0 overflow-x-auto px-4 pt-3">
          <Tabs value={activePath ?? undefined} onValueChange={setSelectedPath}>
            <TabsList aria-label="TODO files">
              {paths.map((path) => (
                <TabsTrigger key={path} value={path}>
                  {path}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      ) : null}
      <div className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
        <div className="flex min-w-0 flex-col gap-3 px-4 py-3">
          {activePath ? (
            <TodoFileView key={activePath} path={activePath} workspaceKey={workspaceKey} />
          ) : (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <ListTodoIcon />
                </EmptyMedia>
                <EmptyTitle>No TODO.md</EmptyTitle>
                <EmptyDescription>Add a TODO.md file to the workspace to track tasks here.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
        </div>
      </div>
    </aside>
  );
}
