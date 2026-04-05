import { useMemo, useState, type FormEvent } from "react";
import {
  DndContext,
  DragOverlay,
  closestCenter,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  horizontalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createTask,
  deleteTask,
  fetchBoardStages,
  fetchConfigBootstrap,
  fetchTasks,
  runTask,
  updateBoardStages,
  updateTask,
} from "../../api";
import type { BoardStage, TaskRecord } from "../../types";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";
import { DeleteConfirmModal } from "../settings/DeleteConfirmModal";
import { BoardStageEditorModal } from "./BoardStageEditorModal";
import { StageColumn } from "./StageColumn";
import { TaskModal, type EditableTask } from "./TaskModal";
import { TaskCardContent } from "./TaskCard";

const EMPTY_TASKS: TaskRecord[] = [];
const EMPTY_STAGES: BoardStage[] = [];

export function BoardPage() {
  const client = useQueryClient();
  const tasksQuery = useQuery({ queryKey: ["tasks"], queryFn: fetchTasks });
  const stagesQuery = useQuery({ queryKey: ["board-stages"], queryFn: fetchBoardStages });
  const configQuery = useQuery({
    queryKey: ["config-bootstrap"],
    queryFn: fetchConfigBootstrap,
    staleTime: 30_000,
  });
  const [editingTask, setEditingTask] = useState<EditableTask | null>(null);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [isBoardEditorOpen, setIsBoardEditorOpen] = useState(false);
  const [taskToDelete, setTaskToDelete] = useState<TaskRecord | null>(null);

  const createTaskMutation = useMutation({
    mutationFn: createTask,
    onSuccess: () => client.invalidateQueries({ queryKey: ["tasks"] }),
  });
  const updateTaskMutation = useMutation({
    mutationFn: ({ taskId, payload }: { taskId: string; payload: Record<string, unknown> }) =>
      updateTask(taskId, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["tasks"] }),
  });
  const runTaskMutation = useMutation({
    mutationFn: runTask,
    onSuccess: () => client.invalidateQueries({ queryKey: ["tasks"] }),
  });
  const updateBoardStagesMutation = useMutation({
    mutationFn: updateBoardStages,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["board-stages"] }),
        client.invalidateQueries({ queryKey: ["tasks"] }),
        client.invalidateQueries({ queryKey: ["bootstrap"] }),
      ]);
    },
  });

  const tasks = tasksQuery.data ?? EMPTY_TASKS;
  const boardStages = stagesQuery.data ?? EMPTY_STAGES;
  const tasksByStage = useMemo(
    () =>
      boardStages.reduce<Record<string, TaskRecord[]>>((acc, stage) => {
        acc[stage.id] = tasks
          .filter((task) => task.stage === stage.id)
          .sort((left, right) => left.position - right.position);
        return acc;
      }, {}),
    [boardStages, tasks],
  );

  const activeTask = activeDragId ? tasks.find((task) => task.task_id === activeDragId) : undefined;
  const activeDragStage = activeDragId
    ? boardStages.find((s) => `sortable-stage:${s.id}` === activeDragId)
    : undefined;

  const handleDragStart = (event: DragStartEvent) => {
    setActiveDragId(String(event.active.id));
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveDragId(null);
    const activeId = String(event.active.id);
    const overId = event.over ? String(event.over.id) : null;

    // Stage reorder
    if (activeId.startsWith("sortable-stage:")) {
      if (!overId || !overId.startsWith("sortable-stage:") || activeId === overId) return;
      const oldIndex = boardStages.findIndex((s) => `sortable-stage:${s.id}` === activeId);
      const newIndex = boardStages.findIndex((s) => `sortable-stage:${s.id}` === overId);
      if (oldIndex === -1 || newIndex === -1) return;
      const reordered = arrayMove(boardStages, oldIndex, newIndex);
      void saveBoardStages(
        reordered.map((s) => ({
          id: s.id,
          name: s.name,
          profile_id: s.profile_id ?? "",
          mode_id: s.mode_id ?? "",
          auto_start: s.auto_start,
        })),
      );
      return;
    }

    // Task move between stages
    const overStage = overId?.startsWith("stage:")
      ? overId.slice("stage:".length)
      : (event.over?.data.current?.stage as string | undefined);
    if (!overStage) return;
    const task = tasks.find((item) => item.task_id === activeId);
    if (!task || task.stage === overStage) return;
    updateTaskMutation.mutate({ taskId: activeId, payload: { stage: overStage } });
  };

  const handleDragCancel = () => {
    setActiveDragId(null);
  };

  const openNewTask = () => {
    const initialStage = boardStages[0]?.id ?? "";
    setEditingTask({
      title: "",
      prompt: "",
      stage: initialStage,
      projectDir: ".",
      sessionId: "",
      profileId: "",
    });
  };

  const openEditTask = (task: TaskRecord) =>
    setEditingTask({
      taskId: task.task_id,
      title: task.title,
      prompt: task.prompt,
      stage: task.stage,
      projectDir: task.project_dir,
      sessionId: task.session_id ?? "",
      profileId: task.profile_id ?? "",
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
          session_id: editingTask.sessionId.trim() === "" ? null : editingTask.sessionId,
          profile_id: editingTask.profileId.trim() === "" ? null : editingTask.profileId,
        },
      });
    } else {
      await createTaskMutation.mutateAsync({
        title: editingTask.title,
        prompt: editingTask.prompt,
        stage: editingTask.stage,
        project_dir: editingTask.projectDir,
        session_id: editingTask.sessionId || undefined,
        profile_id: editingTask.profileId || undefined,
      });
    }
    setEditingTask(null);
  };

  const saveBoardStages = async (
    stages: Array<{
      id: string;
      name: string;
      profile_id: string;
      mode_id: string;
      auto_start: boolean;
    }>,
  ) => {
    await updateBoardStagesMutation.mutateAsync({
      board_stages: stages.map((stage) => ({
        id: stage.id.trim() === "" ? null : stage.id,
        name: stage.name,
        profile_id: stage.profile_id.trim() === "" ? null : stage.profile_id,
        mode_id: stage.mode_id.trim() === "" ? null : stage.mode_id,
        auto_start: stage.auto_start,
      })),
    });
    setIsBoardEditorOpen(false);
  };

  if (tasksQuery.isLoading || stagesQuery.isLoading || configQuery.isLoading) {
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

  if (tasksQuery.isError || stagesQuery.isError || configQuery.isError) {
    return (
      <section className="board-layout">
        <div className="board-layout__header">
          <div>
            <h2 className="board-layout__title">Kanban</h2>
          </div>
        </div>
        <div className="settings-error-banner">
          Failed to load board data.
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
            Tasks move by configured stage order and can auto-start per stage
          </p>
        </div>
        <div className="board-layout__actions">
          <button type="button" className="btn btn--ghost" onClick={() => setIsBoardEditorOpen(true)}>
            Edit Stages
          </button>
          <button type="button" className="btn btn--primary" onClick={openNewTask}>
            + Add Task
          </button>
        </div>
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
          <SortableContext
            items={boardStages.map((s) => `sortable-stage:${s.id}`)}
            strategy={horizontalListSortingStrategy}
          >
            <div className="board-grid">
              {boardStages.map((stage) => (
                <StageColumn
                  key={stage.id}
                  stage={stage}
                  tasks={tasksByStage[stage.id] ?? []}
                  onEdit={openEditTask}
                  onDelete={(taskId) => {
                    const task = tasks.find((t) => t.task_id === taskId);
                    if (task) setTaskToDelete(task);
                  }}
                  onRun={(taskId) => runTaskMutation.mutate(taskId)}
                />
              ))}
            </div>
          </SortableContext>
          <DragOverlay dropAnimation={null}>
            {activeTask ? (
              <article className="task-card task-card--overlay">
                <TaskCardContent task={activeTask} />
              </article>
            ) : null}
            {activeDragStage ? (
              <section className="board-column board-column--overlay">
                <header className="board-column__header">
                  <div className="board-column__heading">
                    <span className="board-column__name">{activeDragStage.name}</span>
                  </div>
                  <span className="board-column__count">
                    {(tasksByStage[activeDragStage.id] ?? []).length}
                  </span>
                </header>
              </section>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      {editingTask ? (
        <TaskModal
          task={editingTask}
          boardStages={boardStages}
          profiles={configQuery.data?.model_profiles ?? []}
          isSaving={createTaskMutation.isPending || updateTaskMutation.isPending}
          onChange={(updates) =>
            setEditingTask((prev) => (prev ? { ...prev, ...updates } : prev))
          }
          onSave={(event) => {
            void saveTask(event);
          }}
          onClose={() => setEditingTask(null)}
        />
      ) : null}

      {taskToDelete ? (
        <DeleteConfirmModal
          title="Delete Task"
          body={
            <>
              Delete task <strong>{taskToDelete.title}</strong>? This cannot be
              undone.
            </>
          }
          onConfirm={async () => {
            await deleteTask(taskToDelete.task_id);
            setTaskToDelete(null);
            await client.invalidateQueries({ queryKey: ["tasks"] });
          }}
          onClose={() => setTaskToDelete(null)}
        />
      ) : null}

      {isBoardEditorOpen ? (
        <BoardStageEditorModal
          stages={boardStages}
          profiles={configQuery.data?.model_profiles ?? []}
          modes={configQuery.data?.modes ?? []}
          isSaving={updateBoardStagesMutation.isPending}
          onSave={saveBoardStages}
          onClose={() => setIsBoardEditorOpen(false)}
        />
      ) : null}
    </section>
  );
}
