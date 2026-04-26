import { type FormEvent } from "react";
import type { BoardStage, ModelProfileView } from "../../types";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "../ui/field";
import { Input } from "../ui/input";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";
import { Textarea } from "../ui/textarea";

export type EditableTask = {
  taskId?: string;
  title: string;
  prompt: string;
  stage: string;
  projectDir: string;
  sessionId: string;
  profileId: string;
};

export function TaskModal({
  task,
  boardStages,
  profiles,
  isSaving,
  onChange,
  onSave,
  onClose,
}: {
  task: EditableTask;
  boardStages: BoardStage[];
  profiles: ModelProfileView[];
  isSaving: boolean;
  onChange: (updates: Partial<EditableTask>) => void;
  onSave: (event: FormEvent<HTMLFormElement>) => void;
  onClose: () => void;
}) {
  const titleId = "task-form-title";
  const promptId = "task-form-prompt";
  const stageId = "task-form-stage";
  const profileId = "task-form-profile";

  return (
    <Dialog open onOpenChange={(open) => {
      if (!open) onClose();
    }}>
      <DialogContent className="task-form-dialog">
        <DialogHeader>
          <DialogTitle>
            {task.taskId ? "Edit Task" : "New Task"}
          </DialogTitle>
        </DialogHeader>

        <form className="task-form" onSubmit={onSave}>
          <div className="task-form__body">
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor={titleId}>Title</FieldLabel>
                <Input
                  id={titleId}
                  className="task-form__input"
                  value={task.title}
                  onChange={(e) => onChange({ title: e.target.value })}
                  required
                  autoFocus
                />
              </Field>

              <Field>
                <FieldLabel htmlFor={promptId}>Prompt</FieldLabel>
                <Textarea
                  id={promptId}
                  className="task-form__textarea"
                  value={task.prompt}
                  onChange={(e) => onChange({ prompt: e.target.value })}
                  required
                />
              </Field>

              <Field>
                <FieldLabel htmlFor={stageId}>Stage</FieldLabel>
                <NativeSelect
                  id={stageId}
                  className="task-form__select"
                  value={task.stage}
                  onChange={(e) => onChange({ stage: e.target.value })}
                  required
                >
                  {boardStages.map((stage) => (
                    <NativeSelectOption key={stage.id} value={stage.id}>
                      {stage.name}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>

              <Field>
                <FieldLabel htmlFor={profileId}>Profile Override</FieldLabel>
                <NativeSelect
                  id={profileId}
                  className="task-form__select"
                  value={task.profileId}
                  onChange={(e) => onChange({ profileId: e.target.value })}
                >
                  <NativeSelectOption value="">Use stage/default runtime</NativeSelectOption>
                  {profiles.map((profile) => (
                    <NativeSelectOption key={profile.id} value={profile.id}>
                      {profile.name}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
            </FieldGroup>
          </div>

          <DialogFooter className="task-form__footer">
            <Button
              type="button"
              variant="ghost"
              className="task-form__action-button"
              onClick={onClose}
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="ghost"
              className="task-form__action-button"
              disabled={isSaving}
            >
              {isSaving ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
