import { useEffect, useState, type FormEvent } from "react";
import type { ModeView } from "../../types";

interface FormState {
  name: string;
  id: string;
  slash_alias: string;
  description: string;
  instructions: string;
}

function initForm(mode?: ModeView): FormState {
  if (mode) {
    return {
      name: mode.name,
      id: mode.id,
      slash_alias: mode.slash_alias,
      description: mode.description,
      instructions: mode.instructions,
    };
  }
  return {
    name: "",
    id: "",
    slash_alias: "",
    description: "",
    instructions: "",
  };
}

export type ModePayload = {
  id?: string | null;
  name: string;
  slash_alias: string;
  description?: string;
  instructions: string;
};

interface Props {
  mode?: ModeView;
  onSave: (payload: ModePayload) => Promise<void>;
  onClose: () => void;
}

export function ModeModal({ mode, onSave, onClose }: Props) {
  const isEdit = !!mode;
  const [form, setForm] = useState<FormState>(() => initForm(mode));
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  function set(updates: Partial<FormState>) {
    setForm((prev) => ({ ...prev, ...updates }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsPending(true);
    setError(null);

    const payload: ModePayload = {
      name: form.name.trim(),
      slash_alias: form.slash_alias.trim(),
      description: form.description.trim(),
      instructions: form.instructions.trim(),
    };

    if (!isEdit && form.id.trim()) {
      payload.id = form.id.trim();
    }

    try {
      await onSave(payload);
    } catch (err) {
      setError((err as Error).message);
      setIsPending(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-card__header">
          <h2 className="modal-card__title">
            {isEdit ? "Edit Mode" : "Add Mode"}
          </h2>
          <button
            type="button"
            className="modal-card__close"
            onClick={onClose}
            disabled={isPending}
          >
            &times;
          </button>
        </div>

        <form className="task-form" onSubmit={handleSubmit}>
          <div className="task-form__field">
            <label className="task-form__label">Name</label>
            <input
              name="mode-name"
              className="task-form__input"
              value={form.name}
              onChange={(e) => set({ name: e.target.value })}
              required
              autoFocus
              placeholder="e.g. Plan"
            />
          </div>

          {!isEdit && (
            <div className="task-form__field">
              <label className="task-form__label">ID (optional)</label>
              <input
                name="mode-id"
                className="task-form__input"
                value={form.id}
                onChange={(e) => set({ id: e.target.value })}
                placeholder="Auto-generated from name"
              />
              <span className="task-form__hint">
                Leave blank to auto-generate from the name.
              </span>
            </div>
          )}

          <div className="task-form__field">
            <label className="task-form__label">Slash command</label>
            <input
              name="mode-slash-alias"
              className="task-form__input"
              value={form.slash_alias}
              onChange={(e) => set({ slash_alias: e.target.value })}
              required
              placeholder="/plan"
            />
            <span className="task-form__hint">
              Used at the start of a chat turn, for example <code>/plan scope this</code>.
            </span>
          </div>

          <div className="task-form__field">
            <label className="task-form__label">Description</label>
            <input
              name="mode-description"
              className="task-form__input"
              value={form.description}
              onChange={(e) => set({ description: e.target.value })}
              placeholder="Short explanation shown in settings and command search"
            />
          </div>

          <div className="task-form__field">
            <label className="task-form__label">Instructions</label>
            <textarea
              name="mode-instructions"
              className="task-form__textarea task-form__textarea--lg"
              value={form.instructions}
              onChange={(e) => set({ instructions: e.target.value })}
              required
              rows={8}
              placeholder="These instructions will be appended inside <active_mode> for that turn."
            />
          </div>

          {error && <div className="task-form__error">{error}</div>}

          <button type="submit" className="task-form__submit" disabled={isPending}>
            {isPending ? "Saving…" : isEdit ? "Save Changes" : "Add Mode"}
          </button>
        </form>
      </div>
    </div>
  );
}
