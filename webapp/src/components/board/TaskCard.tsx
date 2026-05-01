import { useDraggable } from "@dnd-kit/core";
import { ExternalLinkIcon, GripVerticalIcon, ImageIcon, PencilIcon, PlayIcon, Trash2Icon } from "lucide-react";
import type { TaskRecord } from "../../types";
import { Button } from "../ui/button";
import { Card, CardFooter, CardHeader, CardTitle } from "../ui/card";
import { StatusPill } from "../shared/StatusPill";

/** Presentational card body — reused in DragOverlay */
export function TaskCardContent({ task }: { task: TaskRecord }) {
  return (
    <>
      <CardTitle className="task-card__title">{task.title}</CardTitle>
      <p className="task-card__prompt">{task.prompt}</p>
      {task.image_attachments.length > 0 ? (
        <div className="task-card__meta">
          <span className="task-card__attachment-count">
            <ImageIcon aria-hidden="true" />
            {task.image_attachments.length}
          </span>
        </div>
      ) : null}
      {task.last_result_summary ? (
        <pre className="task-card__summary">{task.last_result_summary}</pre>
      ) : null}
    </>
  );
}

export function TaskCard({
  task,
  onEdit,
  onDelete,
  onRun,
  canRun,
}: {
  task: TaskRecord;
  onEdit: () => void;
  onDelete: () => void;
  onRun: () => void;
  canRun: boolean;
}) {
  const isRunning = task.run_status === "running";
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: task.task_id,
    disabled: isRunning,
    data: { taskId: task.task_id, stage: task.stage },
  });

  return (
    <Card
      ref={setNodeRef}
      className={`task-card${isDragging ? " task-card--dragging" : ""}${isRunning ? " task-card--readonly" : ""}`}
    >
      {/* Drag handle — only this region initiates drag */}
      <CardHeader className="task-card__drag-handle" {...listeners} {...attributes}>
        <div className="task-card__chrome-row">
          <GripVerticalIcon className="task-card__grip" aria-hidden="true" />
          <StatusPill status={task.run_status} />
        </div>
        <TaskCardContent task={task} />
      </CardHeader>

      <CardFooter className="app-action-row app-action-row--compact app-action-row--nowrap task-card__actions">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="task-card__action-button"
          onClick={onEdit}
          disabled={isRunning}
        >
          <PencilIcon data-icon="inline-start" />
          Edit
        </Button>
        {canRun ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="task-card__action-button"
            onClick={onRun}
            disabled={isRunning}
          >
            <PlayIcon data-icon="inline-start" />
            Start
          </Button>
        ) : null}
        {task.session_id ? (
          <Button variant="ghost" size="sm" className="task-card__action-button" asChild>
            <a href={`/sessions/${encodeURIComponent(task.session_id)}`}>
              <ExternalLinkIcon data-icon="inline-start" />
              Session
            </a>
          </Button>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="task-card__action-button"
          onClick={onDelete}
          disabled={isRunning}
        >
          <Trash2Icon data-icon="inline-start" />
          Delete
        </Button>
      </CardFooter>
    </Card>
  );
}
