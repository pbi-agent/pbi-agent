import { useDroppable } from "@dnd-kit/core";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { BoardStage, TaskRecord } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { TaskCard } from "./TaskCard";

const TERMINAL_STAGE_ID = "done";

export function StageColumn({
  stage,
  tasks,
  onEdit,
  onDelete,
  onRun,
}: {
  stage: BoardStage;
  tasks: TaskRecord[];
  onEdit: (task: TaskRecord) => void;
  onDelete: (taskId: string) => void;
  onRun: (taskId: string) => void;
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

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <section
      ref={setSortableRef}
      style={style}
      className={`board-column${isOver ? " board-column--drop-over" : ""}${isDragging ? " board-column--dragging" : ""}`}
    >
      <header className="board-column__header">
        <div
          className="board-column__drag-handle"
          {...listeners}
          {...attributes}
        >
          <svg
            className="board-column__grip-icon"
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="currentColor"
            aria-hidden="true"
          >
            <circle cx="4" cy="2" r="1.2" />
            <circle cx="8" cy="2" r="1.2" />
            <circle cx="4" cy="6" r="1.2" />
            <circle cx="8" cy="6" r="1.2" />
            <circle cx="4" cy="10" r="1.2" />
            <circle cx="8" cy="10" r="1.2" />
          </svg>
        </div>
        <div className="board-column__heading">
          <span className="board-column__name">{stage.name}</span>
          <div className="board-column__meta">
            {stage.auto_start ? (
              <span className="board-column__label">auto-start</span>
            ) : null}
            {stage.mode_id ? (
              <span className="board-column__label">command:{stage.mode_id}</span>
            ) : null}
            {stage.profile_id ? (
              <span className="board-column__label">profile:{stage.profile_id}</span>
            ) : null}
          </div>
        </div>
        <span className="board-column__count">{tasks.length}</span>
      </header>
      <div ref={setDropRef} className="board-column__body">
        {tasks.length === 0 ? (
          <EmptyState title="No tasks" />
        ) : (
          tasks.map((task) => (
            <TaskCard
              key={task.task_id}
              task={task}
              onEdit={() => onEdit(task)}
              onDelete={() => onDelete(task.task_id)}
              onRun={() => onRun(task.task_id)}
              canRun={stage.id !== TERMINAL_STAGE_ID}
            />
          ))
        )}
      </div>
    </section>
  );
}
