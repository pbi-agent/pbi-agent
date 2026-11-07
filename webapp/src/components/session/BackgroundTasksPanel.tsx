import { useEffect, useState } from "react";
import { ChevronRightIcon, SquareIcon, XIcon } from "lucide-react";
import { getBackgroundTaskOutput } from "../../api";
import type { BackgroundTask, BackgroundTaskOutput } from "../../types";
import { cn } from "../../lib/utils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "../ui/empty";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "../ui/collapsible";

type Props = {
  sessionId: string | null;
  tasks: BackgroundTask[];
  onKill?: (taskId: string) => Promise<void> | void;
  onClose?: () => void;
};

const PRE_CLASS_NAME =
  "m-0 max-h-80 overflow-auto rounded-sm border border-border bg-muted px-3 py-2 font-mono text-xs leading-normal break-words whitespace-pre-wrap text-foreground";

const STATUS_VARIANT = {
  running: "running",
  completed: "completed",
  failed: "failed",
  killed: "warning",
  timed_out: "warning",
} as const;

const STATUS_LABEL: Record<BackgroundTask["status"], string> = {
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  killed: "Killed",
  timed_out: "Timed out",
};

export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return minutes > 0 ? `${minutes}m ${rest}s` : `${rest}s`;
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

export function BackgroundTasksPanel({ sessionId, tasks, onKill, onClose }: Props) {
  const running = tasks.filter((task) => task.status === "running");
  const now = useNow(running.length > 0);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [outputs, setOutputs] = useState<Record<string, BackgroundTaskOutput>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const elapsedFor = (task: BackgroundTask) =>
    task.status === "running"
      ? Math.max(task.elapsed_seconds, now / 1000 - task.started_at)
      : task.elapsed_seconds;

  const loadOutput = async (taskId: string) => {
    if (!sessionId) return;
    try {
      const result = await getBackgroundTaskOutput(sessionId, taskId);
      setOutputs((prev) => ({ ...prev, [taskId]: result }));
      setErrors((prev) => {
        const next = { ...prev };
        delete next[taskId];
        return next;
      });
    } catch (error) {
      setErrors((prev) => ({
        ...prev,
        [taskId]: error instanceof Error ? error.message : String(error),
      }));
    }
  };

  const toggle = (taskId: string, next: boolean) => {
    setExpanded((prev) => {
      const copy = new Set(prev);
      if (next) copy.add(taskId);
      else copy.delete(taskId);
      return copy;
    });
    if (next) void loadOutput(taskId);
  };

  // Refresh expanded outputs while tasks run or change status.
  const statusKey = tasks.map((t) => `${t.task_id}:${t.status}`).join("|");
  useEffect(() => {
    expanded.forEach((taskId) => void loadOutput(taskId));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusKey, running.length > 0 ? now : 0]);

  const summary = `${running.length} running · ${tasks.length - running.length} finished`;

  return (
    <aside
      id="background-tasks-panel"
      className="flex size-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background"
      aria-label="Background tasks"
    >
      <header data-panel-header="" className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border bg-sidebar px-3">
        <div className="flex min-w-0 flex-col">
          <h2 className="truncate text-sm font-semibold">Background tasks</h2>
          <p className="truncate text-xs text-muted-foreground">{summary}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Close background tasks panel"
            onClick={onClose}
          >
            <XIcon aria-hidden="true" />
          </Button>
        </div>
      </header>
      <div className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
        <div className="flex min-w-0 flex-col gap-2 px-4 py-3">
          {tasks.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyTitle>No background tasks</EmptyTitle>
                <EmptyDescription>
                  Shell commands started in the background appear here.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}
          {tasks.map((task) => {
            const isOpen = expanded.has(task.task_id);
            const output = outputs[task.task_id];
            return (
              <Collapsible
                key={task.task_id}
                open={isOpen}
                onOpenChange={(next) => toggle(task.task_id, next)}
              >
               <div className="min-w-0 overflow-hidden rounded-md border border-border bg-card">
                <div className="flex items-center gap-2 px-3 py-2">
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 cursor-pointer items-start gap-2 rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      aria-label={`Toggle output for ${task.intent || task.task_id}`}
                    >
                      <ChevronRightIcon
                        aria-hidden="true"
                        className="mt-1 size-3.5 shrink-0 text-muted-foreground transition-transform data-[open=true]:rotate-90"
                        data-open={isOpen ? "true" : "false"}
                      />
                      <span className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className="flex min-w-0 items-center gap-2">
                          <Badge variant={STATUS_VARIANT[task.status]} size="meta">
                            {STATUS_LABEL[task.status]}
                            {task.exit_code !== null &&
                            task.exit_code !== undefined &&
                            task.status !== "running"
                              ? ` · exit ${task.exit_code}`
                              : ""}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {task.task_id} · {formatElapsed(elapsedFor(task))}
                          </span>
                        </span>
                        {task.intent ? (
                          <span className="truncate text-sm" title={task.command}>
                            {task.intent}
                          </span>
                        ) : (
                          <code className="truncate font-mono text-xs text-muted-foreground" title={task.command}>
                            {task.command}
                          </code>
                        )}
                      </span>
                    </button>
                  </CollapsibleTrigger>
                  {task.status === "running" ? (
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      disabled={!onKill}
                      aria-label={`Kill background task ${task.intent || task.task_id}`}
                      onClick={() => void onKill?.(task.task_id)}
                    >
                      <SquareIcon data-icon="inline-start" aria-hidden="true" />
                      Kill
                    </Button>
                  ) : null}
                </div>
                <CollapsibleContent>
                 <div className="flex min-w-0 flex-col gap-2 border-t border-border px-3 pt-2 pb-3">
                  {errors[task.task_id] ? (
                    <span role="alert" className="text-xs text-destructive">{errors[task.task_id]}</span>
                  ) : output ? (
                    <>
                      <span className="text-xs font-medium text-muted-foreground">Input</span>
                      <pre className={cn(PRE_CLASS_NAME, "max-h-40")} data-stream="input">
                        {task.command}
                      </pre>
                      <span className="text-xs font-medium text-muted-foreground">Output</span>
                      <pre className={PRE_CLASS_NAME}>
                        {output.stdout || "(no stdout)"}
                      </pre>
                      {output.stderr ? (
                        <pre className={cn(PRE_CLASS_NAME, "text-destructive")} data-stream="stderr">
                          {output.stderr}
                        </pre>
                      ) : null}
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground">Loading output…</span>
                  )}
                 </div>
                </CollapsibleContent>
               </div>
              </Collapsible>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
