import { useDraggable } from "@dnd-kit/core";
import type { TaskRecord } from "../../types";
import { StatusPill } from "../shared/StatusPill";

/** Presentational card body — reused in DragOverlay */
export function TaskCardContent({ task }: { task: TaskRecord }) {
  return (
    <>
      <div className="task-card__top">
        <span className="task-card__title">{task.title}</span>
        <StatusPill status={task.run_status} />
      </div>
      <p className="task-card__prompt">{task.prompt}</p>
      <div className="task-card__meta">
        <span>{task.project_dir}</span>
        <span>{task.session_id ?? "no session"}</span>
      </div>
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
    <article
      ref={setNodeRef}
      className={`task-card${isDragging ? " task-card--dragging" : ""}${isRunning ? " task-card--readonly" : ""}`}
    >
      {/* Drag handle — only this region initiates drag */}
      <div className="task-card__drag-handle" {...listeners} {...attributes}>
        <TaskCardContent task={task} />
      </div>

      <div className="task-card__actions">
        <button type="button" className="btn btn--ghost btn--sm" onClick={onEdit} disabled={isRunning}>
          Edit
        </button>
        {canRun ? (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={onRun}
            disabled={isRunning}
          >
            Start
          </button>
        ) : null}
        {task.session_id ? (
          <a
            className="btn btn--ghost btn--sm"
            href={`/sessions/${encodeURIComponent(task.session_id)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Session
          </a>
        ) : null}
        <button type="button" className="btn btn--danger btn--sm" onClick={onDelete} disabled={isRunning}>
          Delete
        </button>
      </div>
    </article>
  );
}
