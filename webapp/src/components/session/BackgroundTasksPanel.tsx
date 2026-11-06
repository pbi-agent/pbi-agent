import { useEffect, useState } from "react";
import { ChevronRightIcon, SquareIcon, XIcon } from "lucide-react";
import { getBackgroundTaskOutput } from "../../api";
import type { BackgroundTask, BackgroundTaskOutput } from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "../ui/empty";
import { ScrollArea } from "../ui/scroll-area";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "../ui/collapsible";

type Props = {
  sessionId: string | null;
  tasks: BackgroundTask[];
  onKill?: (taskId: string) => Promise<void> | void;
  onClose?: () => void;
};

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
      className="workspace-file-panel"
      aria-label="Background tasks"
    >
      <header className="workspace-file-panel__header">
        <div className="workspace-file-panel__heading">
          <h2>Background tasks</h2>
          <p>{summary}</p>
        </div>
        <div className="workspace-file-panel__actions">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="app-close-icon-button"
            aria-label="Close background tasks panel"
            onClick={onClose}
          >
            <XIcon aria-hidden="true" />
          </Button>
        </div>
      </header>
      <ScrollArea className="min-h-0 flex-1">
        <div className="background-tasks-panel__list">
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
                className="background-tasks-panel__item"
              >
                <div className="background-tasks-panel__row">
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="background-tasks-panel__trigger"
                      aria-label={`Toggle output for ${task.task_id}`}
                    >
                      <ChevronRightIcon
                        aria-hidden="true"
                        className="background-tasks-panel__chevron"
                        data-open={isOpen ? "true" : "false"}
                      />
                      <span className="background-tasks-panel__copy">
                        <span className="background-tasks-panel__title">
                          <Badge variant={STATUS_VARIANT[task.status]} size="meta">
                            {STATUS_LABEL[task.status]}
                            {task.exit_code !== null &&
                            task.exit_code !== undefined &&
                            task.status !== "running"
                              ? ` · exit ${task.exit_code}`
                              : ""}
                          </Badge>
                          <span className="background-tasks-panel__meta">
                            {task.task_id} · {formatElapsed(elapsedFor(task))}
                          </span>
                        </span>
                        <code className="background-tasks-panel__command">{task.command}</code>
                      </span>
                    </button>
                  </CollapsibleTrigger>
                  {task.status === "running" ? (
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      className="tool-result-card__interrupt-button"
                      disabled={!onKill}
                      aria-label={`Kill background task ${task.task_id}`}
                      onClick={() => void onKill?.(task.task_id)}
                    >
                      <SquareIcon data-icon="inline-start" aria-hidden="true" />
                      Kill
                    </Button>
                  ) : null}
                </div>
                <CollapsibleContent className="background-tasks-panel__output">
                  {errors[task.task_id] ? (
                    <span className="composer__follow-up-error">{errors[task.task_id]}</span>
                  ) : output ? (
                    <>
                      <pre className="background-tasks-panel__pre">
                        {output.stdout || "(no stdout)"}
                      </pre>
                      {output.stderr ? (
                        <pre className="background-tasks-panel__pre" data-stream="stderr">
                          {output.stderr}
                        </pre>
                      ) : null}
                    </>
                  ) : (
                    <span className="background-tasks-panel__meta">Loading output…</span>
                  )}
                </CollapsibleContent>
              </Collapsible>
            );
          })}
        </div>
      </ScrollArea>
    </aside>
  );
}
