import { useDraggable } from "@dnd-kit/core";
import { ExternalLinkIcon, GripVerticalIcon, PencilIcon, PlayIcon, SquareIcon, Trash2Icon } from "lucide-react";
import type { TaskRecord } from "../../types";
import { Button } from "../ui/button";
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "../ui/card";
import { StatusPill } from "../shared/StatusPill";
import { cn } from "@/lib/utils";

/** Presentational card body — reused in DragOverlay */
export function TaskCardContent({ task }: { task: TaskRecord }) {
  return (
    <>
      <div className="min-w-0 truncate">
        <CardTitle>{task.title}</CardTitle>
      </div>
      <div className="line-clamp-2">
        <CardDescription>{task.prompt}</CardDescription>
      </div>
      {task.last_result_summary ? (
        <pre className="hidden max-h-20 overflow-y-auto rounded-md bg-muted p-2 font-mono text-xs whitespace-pre-wrap text-muted-foreground group-hover/task:block">
          {task.last_result_summary}
        </pre>
      ) : null}
    </>
  );
}

export function TaskCard({
  task,
  onEdit,
  onDelete,
  onRun,
  onInterrupt,
  activeLiveSessionId = null,
  isInterrupting = false,
  canRun,
}: {
  task: TaskRecord;
  onEdit: () => void;
  onDelete: () => void;
  onRun: () => void;
  onInterrupt?: () => void;
  activeLiveSessionId?: string | null;
  isInterrupting?: boolean;
  canRun: boolean;
}) {
  const hasActiveSession = activeLiveSessionId !== null;
  const isRunning = task.run_status === "running";
  const isReadonly = isRunning || hasActiveSession;
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: task.task_id,
    disabled: isReadonly,
    data: { taskId: task.task_id, stage: task.stage },
  });

  return (
    <div
      ref={setNodeRef}
      data-task-card={task.task_id}
      data-dragging={isDragging ? "true" : undefined}
      data-readonly={isReadonly ? "true" : undefined}
      className={cn("group/task min-w-0 shrink-0", isDragging && "opacity-40")}
    >
    <Card size="sm">
      {/* Drag handle — only this region initiates drag */}
      <CardHeader
        className={cn("min-w-0", isReadonly ? "cursor-default" : "cursor-grab")}
        {...listeners}
        {...attributes}
      >
        <div className="flex min-w-0 flex-col gap-2">
        <div className="flex w-full min-w-0 items-center justify-between gap-2">
          <GripVerticalIcon className="text-muted-foreground" aria-hidden="true" />
          <StatusPill status={task.run_status} size="meta" />
        </div>
        <TaskCardContent task={task} />
        </div>
      </CardHeader>

      <CardFooter className="hidden group-focus-within/task:flex group-hover/task:flex">
        <div className="flex w-full flex-nowrap justify-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
         
          onClick={onEdit}
          disabled={isReadonly}
        >
          <PencilIcon data-icon="inline-start" />
          Edit
        </Button>
        {hasActiveSession ? (
          <Button
            type="button"
            variant="destructive"
            size="sm"
            onClick={onInterrupt}
            disabled={isInterrupting || !onInterrupt}
            aria-label={`Stop ${task.title}`}
          >
            <SquareIcon data-icon="inline-start" />
            Stop
          </Button>
        ) : canRun ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
           
            onClick={onRun}
            disabled={isRunning}
          >
            <PlayIcon data-icon="inline-start" />
            Start
          </Button>
        ) : null}
        {task.session_id ? (
          <Button variant="ghost" size="sm" asChild>
            <a href={`/sessions/${encodeURIComponent(task.session_id)}`}>
              <ExternalLinkIcon data-icon="inline-start" />
              Session
            </a>
          </Button>
        ) : null}
        <Button
          type="button"
          variant="destructive"
          size="sm"
          onClick={onDelete}
          disabled={isReadonly}
        >
          <Trash2Icon data-icon="inline-start" />
          Delete
        </Button>
        </div>
      </CardFooter>
    </Card>
    </div>
  );
}
