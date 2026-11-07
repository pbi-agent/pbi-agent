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
import { AlertTriangleIcon, Columns3Icon, PlusIcon, Settings2Icon } from "lucide-react";
import {
  ApiError,
  createTask,
  deleteTask,
  fetchBoardStages,
  fetchConfigBootstrap,
  fetchTasks,
  interruptSession,
  runTask,
  updateBoardStages,
  updateTask,
  uploadTaskImages,
} from "../../api";
import type { BoardStage, TaskRecord } from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Card, CardHeader, CardTitle } from "../ui/card";
import { Separator } from "../ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";
import { DeleteConfirmModal } from "../settings/DeleteConfirmModal";
import { BoardStageEditorModal } from "./BoardStageEditorModal";
import { StageColumn } from "./StageColumn";
import { sanitizeEditableBoardStages, toEditableBoardStages } from "./stageConfig";
import { TaskModal, type EditableTask } from "./TaskModal";
import { TaskCardContent } from "./TaskCard";

const EMPTY_TASKS: TaskRecord[] = [];
const EMPTY_STAGES: BoardStage[] = [];
const BACKLOG_STAGE_ID = "backlog";
const DONE_STAGE_ID = "done";

function toBoardStagePayload(
  stages: Array<{
    id: string;
    name: string;
    profile_id: string;
    command_id: string;
    auto_start: boolean;
  }>,
) {
  return {
    board_stages: stages.map((stage) => ({
      id: stage.id.trim() === "" ? null : stage.id,
      name: stage.name,
      profile_id: stage.profile_id.trim() === "" ? null : stage.profile_id,
      command_id: stage.command_id.trim() === "" ? null : stage.command_id,
      auto_start: stage.auto_start,
    })),
  };
}

function isUnknownStageReferenceError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 400 && (
    error.message.includes("Unknown profile ID") || error.message.includes("Unknown command ID")
  );
}

function isMissingRunnableStageError(error: unknown): error is ApiError {
  return error instanceof ApiError
    && error.status === 400
    && error.message.includes("Backlog tasks require a runnable board stage");
}

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
  const [boardEditorStartsWithNewStage, setBoardEditorStartsWithNewStage] = useState(false);
  const [isCreateStagePromptOpen, setIsCreateStagePromptOpen] = useState(false);
  const [taskToDelete, setTaskToDelete] = useState<TaskRecord | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

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
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["tasks"] }),
        client.invalidateQueries({ queryKey: ["sessions"] }),
      ]);
    },
  });
  const interruptTaskMutation = useMutation({
    mutationFn: interruptSession,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["tasks"] }),
        client.invalidateQueries({ queryKey: ["sessions"] }),
        client.invalidateQueries({ queryKey: ["bootstrap"] }),
      ]);
    },
    onError: (error) => {
      setRunError(error instanceof Error ? error.message : "Failed to interrupt task session.");
    },
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
  const profiles = configQuery.data?.model_profiles ?? [];
  const commands = configQuery.data?.commands ?? [];
  const hasRunnableBoardStage = boardStages.some(
    (stage) => stage.id !== BACKLOG_STAGE_ID && stage.id !== DONE_STAGE_ID,
  );
  const tasksByStage = useMemo(
    () =>
      boardStages.reduce<Record<string, TaskRecord[]>>((acc, stage) => {
        acc[stage.id] = tasks
          .filter((task) => task.stage === stage.id)
          .sort((left, right) => {
            if (stage.id === DONE_STAGE_ID) {
              return Date.parse(right.created_at) - Date.parse(left.created_at);
            }
            return left.position - right.position;
          });
        return acc;
      }, {}),
    [boardStages, tasks],
  );
  const activeTaskSessionIds = useMemo(
    () =>
      tasks.reduce<Record<string, string>>((acc, task) => {
        if (task.run_status === "running" && task.session_id) {
          acc[task.task_id] = task.session_id;
        }
        return acc;
      }, {}),
    [tasks],
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
      void saveBoardStages(toEditableBoardStages(reordered));
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
      imageAttachments: [],
      imageFiles: [],
      imageError: null,
    });
  };

  const openBoardEditor = (startWithNewStage = false) => {
    setBoardEditorStartsWithNewStage(startWithNewStage);
    setIsBoardEditorOpen(true);
  };

  const closeBoardEditor = () => {
    setIsBoardEditorOpen(false);
    setBoardEditorStartsWithNewStage(false);
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
      imageAttachments: task.image_attachments,
      imageFiles: [],
      imageError: null,
    });

  const saveTask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingTask) return;
    try {
      const uploadedImages = editingTask.imageFiles.length > 0
        ? await uploadTaskImages(editingTask.imageFiles.map((image) => image.file))
        : [];
      const imageUploadIds = [
        ...editingTask.imageAttachments.map((attachment) => attachment.upload_id),
        ...uploadedImages.map((attachment) => attachment.upload_id),
      ];
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
            image_upload_ids: imageUploadIds,
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
          image_upload_ids: imageUploadIds,
        });
      }
      setEditingTask(null);
    } catch (error) {
      setEditingTask((current) => current
        ? { ...current, imageError: error instanceof Error ? error.message : "Failed to save task images." }
        : current);
    }
  };

  const saveBoardStages = async (
    stages: Array<{
      id: string;
      name: string;
      profile_id: string;
      command_id: string;
      auto_start: boolean;
    }>,
  ) => {
    try {
      await updateBoardStagesMutation.mutateAsync(toBoardStagePayload(stages));
    } catch (error) {
      if (!isUnknownStageReferenceError(error)) {
        throw error;
      }
      const freshConfig = await fetchConfigBootstrap();
      client.setQueryData(["config-bootstrap"], freshConfig);
      await updateBoardStagesMutation.mutateAsync(
        toBoardStagePayload(
          sanitizeEditableBoardStages(stages, freshConfig.model_profiles, freshConfig.commands),
        ),
      );
    }
    closeBoardEditor();
  };

  const handleRunTask = (taskId: string) => {
    const task = tasks.find((item) => item.task_id === taskId);
    if (!task) {
      return;
    }
    setRunError(null);
    if (task.stage === BACKLOG_STAGE_ID && !hasRunnableBoardStage) {
      setIsCreateStagePromptOpen(true);
      return;
    }
    runTaskMutation.mutate(taskId, {
      onError: (error) => {
        if (isMissingRunnableStageError(error)) {
          setIsCreateStagePromptOpen(true);
          return;
        }
        setRunError(error.message);
      },
    });
  };

  const handleInterruptTask = (liveSessionId: string) => {
    setRunError(null);
    interruptTaskMutation.mutate(liveSessionId);
  };

  if (tasksQuery.isLoading || stagesQuery.isLoading || configQuery.isLoading) {
    return (
      <section className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex min-h-20 shrink-0 items-center justify-between gap-4 px-6 py-5">
          <div>
            <h2 className="font-heading text-lg font-medium">Kanban</h2>
          </div>
        </div>
        <Separator />
        <div className="flex flex-1 items-center justify-center p-6">
          <LoadingSpinner size="lg" />
        </div>
      </section>
    );
  }

  if (tasksQuery.isError || stagesQuery.isError || configQuery.isError) {
    return (
      <section className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex min-h-20 shrink-0 items-center justify-between gap-4 px-6 py-5">
          <div>
            <h2 className="font-heading text-lg font-medium">Kanban</h2>
          </div>
        </div>
        <Separator />
        <Alert variant="destructive" className="m-4 w-auto">
          <AlertTriangleIcon />
          <AlertDescription>
            Failed to load board data.
          </AlertDescription>
        </Alert>
      </section>
    );
  }

  return (
    <section className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex min-h-20 shrink-0 flex-col items-stretch justify-between gap-4 px-6 py-5 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="font-heading text-lg font-medium">Kanban</h2>
          <p className="text-sm text-muted-foreground">
            Tasks move by configured stage order and can auto-start per stage
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 sm:justify-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => openBoardEditor(false)}
          >
            <Settings2Icon data-icon="inline-start" />
            Edit Stages
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={openNewTask}
          >
            <PlusIcon data-icon="inline-start" />
            Add Task
          </Button>
        </div>
      </div>

      <Separator />

      {runError ? (
        <Alert variant="destructive" className="mx-4 mt-4 w-auto">
          <AlertTriangleIcon />
          <AlertDescription>{runError}</AlertDescription>
        </Alert>
      ) : null}

      {tasks.length === 0 ? (
        <div className="flex flex-1 items-center justify-center p-6">
        <EmptyState
          title="No tasks yet"
          description="Create your first task to get started"
          action={
            <Button type="button" onClick={openNewTask}>
              <PlusIcon data-icon="inline-start" />
              Add Task
            </Button>
          }
        />
        </div>
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
            <div className="flex min-h-0 flex-1 items-start gap-4 overflow-x-auto px-4 py-5" data-board-grid>
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
                  activeTaskLiveSessionIds={activeTaskSessionIds}
                  interruptingLiveSessionId={
                    interruptTaskMutation.isPending ? interruptTaskMutation.variables : null
                  }
                  onRun={handleRunTask}
                  onInterrupt={handleInterruptTask}
                />
              ))}
            </div>
          </SortableContext>
          <DragOverlay dropAnimation={null}>
            {activeTask ? (
              <div className="pointer-events-none scale-105 cursor-grabbing rounded-xl shadow-lg">
                <Card size="sm">
                  <CardHeader>
                    <div className="flex min-w-0 flex-col gap-2">
                      <TaskCardContent task={activeTask} />
                    </div>
                  </CardHeader>
                </Card>
              </div>
            ) : null}
            {activeDragStage ? (
              <div className="pointer-events-none scale-105 cursor-grabbing rounded-xl shadow-lg">
                <Card>
                  <CardHeader>
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="min-w-0 flex-1 truncate">
                        <CardTitle>{activeDragStage.name}</CardTitle>
                      </div>
                      <Badge variant="outline">
                        {(tasksByStage[activeDragStage.id] ?? []).length}
                      </Badge>
                    </div>
                  </CardHeader>
                </Card>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      {editingTask ? (
        <TaskModal
          task={editingTask}
          boardStages={boardStages}
          profiles={profiles}
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
          profiles={profiles}
          commands={commands}
          startWithNewStage={boardEditorStartsWithNewStage}
          isSaving={updateBoardStagesMutation.isPending}
          onSave={saveBoardStages}
          onClose={closeBoardEditor}
        />
      ) : null}

      {isCreateStagePromptOpen ? (
        <Dialog open onOpenChange={(open) => setIsCreateStagePromptOpen(open)}>
          <DialogContent>
            <DialogHeader>
              <Columns3Icon aria-hidden="true" className="text-muted-foreground" />
              <DialogTitle>Create Runnable Stage</DialogTitle>
              <DialogDescription>
                This board only has <strong>Backlog</strong> and <strong>Done</strong>.
                Add a stage between them before starting backlog tasks.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsCreateStagePromptOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setIsCreateStagePromptOpen(false);
                  openBoardEditor(true);
                }}
              >
                Create Stage
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </section>
  );
}
