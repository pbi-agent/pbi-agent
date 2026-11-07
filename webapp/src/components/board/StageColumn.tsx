import { useDroppable } from "@dnd-kit/core";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVerticalIcon } from "lucide-react";
import type { BoardStage, TaskRecord } from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { EmptyState } from "../shared/EmptyState";
import { cn } from "@/lib/utils";
import { TaskCard } from "./TaskCard";

const TERMINAL_STAGE_ID = "done";

export function StageColumn({
  stage,
  tasks,
  activeTaskLiveSessionIds = {},
  interruptingLiveSessionId = null,
  onEdit,
  onDelete,
  onRun,
  onInterrupt,
}: {
  stage: BoardStage;
  tasks: TaskRecord[];
  activeTaskLiveSessionIds?: Record<string, string>;
  interruptingLiveSessionId?: string | null;
  onEdit: (task: TaskRecord) => void;
  onDelete: (taskId: string) => void;
  onRun: (taskId: string) => void;
  onInterrupt?: (liveSessionId: string) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef: setSortableRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: `sortable-stage:${stage.id}` });

  const { isOver, setNodeRef: setDropRef } = useDroppable({
    id: `stage:${stage.id}`,
    data: { stage: stage.id },
  });

  // dnd-kit sortable transform/transition are dynamic per frame; no class-based equivalent.
  /* eslint-disable shadcn/no-inline-styles */
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  /* eslint-enable shadcn/no-inline-styles */

  return (
    <div
      ref={setSortableRef}
      style={style}
      data-stage-column={stage.id}
      data-drop-over={isOver ? "true" : undefined}
      data-dragging={isDragging ? "true" : undefined}
      className={cn("flex max-h-full min-w-80 flex-1 basis-80 flex-col", isDragging && "opacity-40")}
    >
    <Card className="min-h-48 flex-1">
      <CardHeader>
        <div className="flex min-w-0 items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="cursor-grab"
          aria-label={`Reorder ${stage.name} stage`}
          {...listeners}
          {...attributes}
        >
          <GripVerticalIcon aria-hidden="true" />
        </Button>
        <div className="min-w-0 flex-1 truncate">
          <CardTitle>{stage.name}</CardTitle>
        </div>
        <Badge variant={isOver ? "default" : "outline"}>{tasks.length}</Badge>
        </div>
      </CardHeader>
      <Separator />
      <CardContent ref={setDropRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-3">
        {tasks.length === 0 ? (
          <EmptyState title="No tasks" />
        ) : (
          tasks.map((task) => {
            const activeLiveSessionId = activeTaskLiveSessionIds[task.task_id] ?? null;
            return (
              <TaskCard
                key={task.task_id}
                task={task}
                activeLiveSessionId={activeLiveSessionId}
                isInterrupting={interruptingLiveSessionId === activeLiveSessionId}
                onEdit={() => onEdit(task)}
                onDelete={() => onDelete(task.task_id)}
                onRun={() => onRun(task.task_id)}
                onInterrupt={activeLiveSessionId ? () => onInterrupt?.(activeLiveSessionId) : undefined}
                canRun={stage.id !== TERMINAL_STAGE_ID}
              />
            );
          })
        )}
        </div>
      </CardContent>
    </Card>
    </div>
  );
}
