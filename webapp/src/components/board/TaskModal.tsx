import { useEffect, type FormEvent } from "react";

export type EditableTask = {
  taskId?: string;
  title: string;
  prompt: string;
  stage: "backlog" | "plan" | "review";
  projectDir: string;
  sessionId: string;
};

export function TaskModal({
  task,
  isSaving,
  onChange,
  onSave,
  onClose,
}: {
  task: EditableTask;
  isSaving: boolean;
  onChange: (updates: Partial<EditableTask>) => void;
  onSave: (event: FormEvent<HTMLFormElement>) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-card__header">
          <h2 className="modal-card__title">
            {task.taskId ? "Edit Task" : "New Task"}
          </h2>
          <button type="button" className="modal-card__close" onClick={onClose}>
            &times;
          </button>
        </div>

        <form className="task-form" onSubmit={onSave}>
          <div className="task-form__field">
            <label className="task-form__label">Title</label>
            <input
              className="task-form__input"
              value={task.title}
              onChange={(e) => onChange({ title: e.target.value })}
              required
              autoFocus
            />
          </div>

          <div className="task-form__field">
            <label className="task-form__label">Prompt</label>
            <textarea
              className="task-form__textarea"
              value={task.prompt}
              onChange={(e) => onChange({ prompt: e.target.value })}
              required
            />
          </div>

          <div className="task-form__field">
            <label className="task-form__label">Stage</label>
            <select
              className="task-form__select"
              value={task.stage}
              onChange={(e) => onChange({ stage: e.target.value as EditableTask["stage"] })}
            >
              <option value="backlog">Backlog</option>
              <option value="plan">Plan</option>
              <option value="review">Review</option>
            </select>
          </div>

          <div className="task-form__field">
            <label className="task-form__label">Project Directory</label>
            <input
              className="task-form__input"
              value={task.projectDir}
              onChange={(e) => onChange({ projectDir: e.target.value })}
            />
          </div>

          <div className="task-form__field">
            <label className="task-form__label">Session ID</label>
            <input
              className="task-form__input"
              value={task.sessionId}
              onChange={(e) => onChange({ sessionId: e.target.value })}
              placeholder="Optional"
            />
          </div>

          <button
            type="submit"
            className="task-form__submit"
            disabled={isSaving}
          >
            {isSaving ? "Saving..." : "Save Task"}
          </button>
        </form>
      </div>
    </div>
  );
}
