import { useDraggable } from "@dnd-kit/core";
import type { TaskRecord } from "../../types";
import { StatusPill } from "../shared/StatusPill";

export function TaskCard({
  task,
  onEdit,
  onDelete,
  onRun,
}: {
  task: TaskRecord;
  onEdit: () => void;
  onDelete: () => void;
  onRun: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: task.task_id,
    disabled: task.stage === "processing",
    data: { taskId: task.task_id, stage: task.stage },
  });

  const style =
    transform != null
      ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
      : undefined;

  return (
    <article
      ref={setNodeRef}
      className={`task-card${isDragging ? " task-card--dragging" : ""}${task.stage === "processing" ? " task-card--readonly" : ""}`}
      style={style}
      {...listeners}
      {...attributes}
    >
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

      <div className="task-card__actions">
        <button type="button" className="btn btn--ghost btn--sm" onClick={onEdit}>
          Edit
        </button>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={onRun}
          disabled={task.run_status === "running"}
        >
          Run
        </button>
        <button type="button" className="btn btn--danger btn--sm" onClick={onDelete}>
          Delete
        </button>
      </div>
    </article>
  );
}
