import { useDroppable } from "@dnd-kit/core";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVerticalIcon } from "lucide-react";
import type { BoardStage, TaskRecord } from "../../types";
import { Badge } from "../ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
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
    <Card
      ref={setSortableRef}
      style={style}
      className={`board-column${isOver ? " board-column--drop-over" : ""}${isDragging ? " board-column--dragging" : ""}`}
    >
      <CardHeader className="board-column__header">
        <div
          className="board-column__drag-handle"
          {...listeners}
          {...attributes}
        >
          <GripVerticalIcon className="board-column__grip-icon" aria-hidden="true" />
        </div>
        <div className="board-column__heading">
          <CardTitle className="board-column__name">{stage.name}</CardTitle>
          <div className="board-column__meta">
            {stage.auto_start ? (
              <Badge variant="secondary" className="board-column__label">auto-start</Badge>
            ) : null}
            {stage.command_id ? (
              <Badge variant="outline" className="board-column__label">command:{stage.command_id}</Badge>
            ) : null}
            {stage.profile_id ? (
              <Badge variant="outline" className="board-column__label">profile:{stage.profile_id}</Badge>
            ) : null}
          </div>
        </div>
        <Badge variant="secondary" className="board-column__count">{tasks.length}</Badge>
      </CardHeader>
      <CardContent ref={setDropRef} className="board-column__body">
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
      </CardContent>
    </Card>
  );
}
