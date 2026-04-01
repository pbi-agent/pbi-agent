import { useDroppable } from "@dnd-kit/core";
import type { TaskRecord } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { TaskCard } from "./TaskCard";

const BOARD_STAGES = ["backlog", "plan", "processing", "review"] as const;

function formatStageLabel(stage: string): string {
  return stage.charAt(0).toUpperCase() + stage.slice(1);
}

export function StageColumn({
  stage,
  tasks,
  onEdit,
  onDelete,
  onRun,
}: {
  stage: (typeof BOARD_STAGES)[number];
  tasks: TaskRecord[];
  onEdit: (task: TaskRecord) => void;
  onDelete: (taskId: string) => void;
  onRun: (taskId: string) => void;
}) {
  const { isOver, setNodeRef } = useDroppable({
    id: `stage:${stage}`,
    data: { stage },
    disabled: stage === "processing",
  });

  return (
    <section
      ref={setNodeRef}
      className={`board-column${isOver ? " board-column--drop-over" : ""}`}
    >
      <header className="board-column__header">
        <span className="board-column__name">
          {formatStageLabel(stage)}
          {stage === "processing" ? (
            <span className="board-column__label">auto</span>
          ) : null}
        </span>
        <span className="board-column__count">{tasks.length}</span>
      </header>
      <div className="board-column__body">
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
            />
          ))
        )}
      </div>
    </section>
  );
}
