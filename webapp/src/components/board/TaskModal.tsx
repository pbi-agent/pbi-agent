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
  return (
    <Dialog open onOpenChange={(open) => {
      if (!open) onClose();
    }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {task.taskId ? "Edit Task" : "New Task"}
          </DialogTitle>
        </DialogHeader>

        <form className="task-form" onSubmit={onSave}>
          <FieldGroup>
          <Field>
            <FieldLabel>Title</FieldLabel>
            <Input
              className="task-form__input"
              value={task.title}
              onChange={(e) => onChange({ title: e.target.value })}
              required
              autoFocus
            />
          </Field>

          <Field>
            <FieldLabel>Prompt</FieldLabel>
            <Textarea
              className="task-form__textarea"
              value={task.prompt}
              onChange={(e) => onChange({ prompt: e.target.value })}
              required
            />
          </Field>

          <Field>
            <FieldLabel>Stage</FieldLabel>
            <NativeSelect
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
            <FieldLabel>Profile Override</FieldLabel>
            <NativeSelect
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

          <DialogFooter className="task-form__footer">
            <Button type="button" variant="outline" onClick={onClose} disabled={isSaving}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? "Saving..." : "Save Task"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
