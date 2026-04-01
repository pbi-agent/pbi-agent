import { useMemo, useState, type FormEvent } from "react";
import { DndContext, DragOverlay, closestCenter, type DragStartEvent, type DragEndEvent } from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createTask, deleteTask, fetchTasks, runTask, updateTask } from "../../api";
import type { TaskRecord } from "../../types";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";
import { StageColumn } from "./StageColumn";
import { TaskModal, type EditableTask } from "./TaskModal";
import { TaskCardContent } from "./TaskCard";

const BOARD_STAGES = ["backlog", "plan", "processing", "review"] as const;

export function BoardPage() {
  const client = useQueryClient();
  const tasksQuery = useQuery({ queryKey: ["tasks"], queryFn: fetchTasks });
  const [editingTask, setEditingTask] = useState<EditableTask | null>(null);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);

  const createTaskMutation = useMutation({
    mutationFn: createTask,
    onSuccess: () => client.invalidateQueries({ queryKey: ["tasks"] }),
  });
  const updateTaskMutation = useMutation({
    mutationFn: ({ taskId, payload }: { taskId: string; payload: Record<string, unknown> }) =>
      updateTask(taskId, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["tasks"] }),
  });
  const deleteTaskMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: () => client.invalidateQueries({ queryKey: ["tasks"] }),
  });
  const runTaskMutation = useMutation({
    mutationFn: runTask,
    onSuccess: () => client.invalidateQueries({ queryKey: ["tasks"] }),
  });

  const tasks = tasksQuery.data ?? [];
  const tasksByStage = useMemo(
    () =>
      BOARD_STAGES.reduce<Record<string, TaskRecord[]>>((acc, stage) => {
        acc[stage] = tasks
          .filter((t) => t.stage === stage)
          .sort((a, b) => a.position - b.position);
        return acc;
      }, {}),
    [tasks],
  );

  const activeTask = activeDragId ? tasks.find((t) => t.task_id === activeDragId) : undefined;

  const handleDragStart = (event: DragStartEvent) => {
    setActiveDragId(String(event.active.id));
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveDragId(null);
    const taskId = String(event.active.id);
    const overStage = event.over?.data.current?.stage as TaskRecord["stage"] | undefined;
    if (!overStage || overStage === "processing") return;
    const task = tasks.find((t) => t.task_id === taskId);
    if (!task || task.stage === overStage) return;
    updateTaskMutation.mutate({ taskId, payload: { stage: overStage } });
  };

  const handleDragCancel = () => {
    setActiveDragId(null);
  };

  const openNewTask = () =>
    setEditingTask({ title: "", prompt: "", stage: "backlog", projectDir: ".", sessionId: "" });

  const openEditTask = (task: TaskRecord) =>
    setEditingTask({
      taskId: task.task_id,
      title: task.title,
      prompt: task.prompt,
      stage: task.stage === "processing" ? "review" : task.stage,
      projectDir: task.project_dir,
      sessionId: task.session_id ?? "",
    });

  const saveTask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingTask) return;
    if (editingTask.taskId) {
      await updateTaskMutation.mutateAsync({
        taskId: editingTask.taskId,
        payload: {
          title: editingTask.title,
          prompt: editingTask.prompt,
          stage: editingTask.stage,
          project_dir: editingTask.projectDir,
          session_id: editingTask.sessionId || undefined,
          clear_session_id: editingTask.sessionId.trim() === "",
        },
      });
    } else {
      await createTaskMutation.mutateAsync({
        title: editingTask.title,
        prompt: editingTask.prompt,
        stage: editingTask.stage,
        project_dir: editingTask.projectDir,
        session_id: editingTask.sessionId || undefined,
      });
    }
    setEditingTask(null);
  };

  if (tasksQuery.isLoading) {
    return (
      <section className="board-layout">
        <div className="board-layout__header">
          <div>
            <h2 className="board-layout__title">Kanban</h2>
          </div>
        </div>
        <div className="center-spinner">
          <LoadingSpinner size="lg" />
        </div>
      </section>
    );
  }

  return (
    <section className="board-layout">
      <div className="board-layout__header">
        <div>
          <h2 className="board-layout__title">Kanban</h2>
          <p className="board-layout__subtitle">
            Tasks update live via the event stream
          </p>
        </div>
        <button type="button" className="btn btn--primary" onClick={openNewTask}>
          + Add Task
        </button>
      </div>

      {tasks.length === 0 ? (
        <EmptyState
          title="No tasks yet"
          description="Create your first task to get started"
          action={
            <button type="button" className="btn btn--primary" onClick={openNewTask}>
              + Add Task
            </button>
          }
        />
      ) : (
        <DndContext
          collisionDetection={closestCenter}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onDragCancel={handleDragCancel}
        >
          <div className="board-grid">
            {BOARD_STAGES.map((stage) => (
              <StageColumn
                key={stage}
                stage={stage}
                tasks={tasksByStage[stage] ?? []}
                onEdit={openEditTask}
                onDelete={(taskId) => deleteTaskMutation.mutate(taskId)}
                onRun={(taskId) => runTaskMutation.mutate(taskId)}
              />
            ))}
          </div>
          <DragOverlay dropAnimation={null}>
            {activeTask ? (
              <article className="task-card task-card--overlay">
                <TaskCardContent task={activeTask} />
              </article>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      {editingTask ? (
        <TaskModal
          task={editingTask}
          isSaving={createTaskMutation.isPending || updateTaskMutation.isPending}
          onChange={(updates) =>
            setEditingTask((prev) => (prev ? { ...prev, ...updates } : prev))
          }
          onSave={saveTask}
          onClose={() => setEditingTask(null)}
        />
      ) : null}
    </section>
  );
}
