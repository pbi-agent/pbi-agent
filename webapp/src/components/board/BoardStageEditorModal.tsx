import { useEffect, useState, type FormEvent } from "react";
import { ArrowDownIcon, ArrowUpIcon, PlusIcon, Trash2Icon } from "lucide-react";
import type { BoardStage, CommandView, ModelProfileView } from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "../ui/field";
import { Input } from "../ui/input";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";
import { type EditableBoardStage, toEditableBoardStages } from "./stageConfig";

const BACKLOG_STAGE_ID = "backlog";
const DONE_STAGE_ID = "done";

function isFixedStage(stageId: string): boolean {
  return stageId === BACKLOG_STAGE_ID || stageId === DONE_STAGE_ID;
}

function buildInitialItems(
  stages: BoardStage[],
  startWithNewStage: boolean,
): EditableBoardStage[] {
  const items = toEditableBoardStages(stages);
  if (!startWithNewStage) {
    return items;
  }
  const nextStage: EditableBoardStage = {
    id: "",
    name: "",
    profile_id: "",
    command_id: "",
    auto_start: false,
  };
  const doneIndex = items.findIndex((item) => item.id === DONE_STAGE_ID);
  if (doneIndex === -1) {
    return [...items, nextStage];
  }
  const nextItems = [...items];
  nextItems.splice(doneIndex, 0, nextStage);
  return nextItems;
}

export function BoardStageEditorModal({
  stages,
  profiles,
  commands,
  startWithNewStage = false,
  isSaving,
  onSave,
  onClose,
}: {
  stages: BoardStage[];
  profiles: ModelProfileView[];
  commands: CommandView[];
  startWithNewStage?: boolean;
  isSaving: boolean;
  onSave: (stages: EditableBoardStage[]) => Promise<void>;
  onClose: () => void;
}) {
  const [items, setItems] = useState<EditableBoardStage[]>(() =>
    buildInitialItems(stages, startWithNewStage),
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setItems(buildInitialItems(stages, startWithNewStage));
  }, [stages, startWithNewStage]);

  const updateItem = (index: number, updates: Partial<EditableBoardStage>) => {
    setItems((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...updates } : item
    )));
  };

  const moveItem = (index: number, direction: -1 | 1) => {
    setItems((current) => {
      if (isFixedStage(current[index]?.id ?? "")) return current;
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= current.length) return current;
      if (isFixedStage(current[targetIndex]?.id ?? "")) return current;
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(targetIndex, 0, item);
      return next;
    });
  };

  const addStage = () => {
    setItems((current) => {
      const nextStage: EditableBoardStage = {
        id: "",
        name: "",
        profile_id: "",
        command_id: "",
        auto_start: false,
      };
      const doneIndex = current.findIndex((item) => item.id === DONE_STAGE_ID);
      if (doneIndex === -1) return [...current, nextStage];
      const next = [...current];
      next.splice(doneIndex, 0, nextStage);
      return next;
    });
  };

  const removeStage = (index: number) => {
    setItems((current) => {
      if (isFixedStage(current[index]?.id ?? "")) return current;
      return current.filter((_, itemIndex) => itemIndex !== index);
    });
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (items.length === 0) {
      setError("Board must contain at least one stage.");
      return;
    }
    try {
      await onSave(items);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => {
      if (!open && !isSaving) onClose();
    }}>
      <DialogContent className="modal-card--board-editor">
        <DialogHeader>
          <DialogTitle>Board Stages</DialogTitle>
        </DialogHeader>

        <form
          className="task-form"
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
        >
          <div className="board-stage-editor">
            {items.map((item, index) => {
              const fixedStage = isFixedStage(item.id);
              const fixedStageLabel = item.id === BACKLOG_STAGE_ID
                ? "Backlog stays first and never runs directly."
                : item.id === DONE_STAGE_ID
                  ? "Done stays last and is archive-only."
                  : null;

              return (
                <div key={`${item.id || "new"}-${index}`} className="board-stage-editor__row">
                <div className="board-stage-editor__ordering">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="board-stage-editor__icon-button"
                    onClick={() => moveItem(index, -1)}
                    disabled={index === 0 || isSaving || fixedStage}
                  >
                    <ArrowUpIcon />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="board-stage-editor__icon-button"
                    onClick={() => moveItem(index, 1)}
                    disabled={index === items.length - 1 || isSaving || fixedStage}
                  >
                    <ArrowDownIcon />
                  </Button>
                </div>

                <FieldGroup className="board-stage-editor__fields">
                  <Field>
                    <FieldLabel>Name</FieldLabel>
                    <Input
                      className="task-form__input"
                      value={item.name}
                      onChange={(event) => updateItem(index, { name: event.target.value })}
                      required
                      disabled={fixedStage}
                    />
                  </Field>
                  {fixedStageLabel ? (
                    <FieldDescription>{fixedStageLabel}</FieldDescription>
                  ) : null}

                  <div className="task-form__row">
                    <Field>
                      <FieldLabel>Profile</FieldLabel>
                      <NativeSelect
                        className="task-form__select"
                        value={item.profile_id}
                        onChange={(event) => updateItem(index, { profile_id: event.target.value })}
                        disabled={fixedStage}
                      >
                        <NativeSelectOption value="">No default profile</NativeSelectOption>
                        {profiles.map((profile) => (
                          <NativeSelectOption key={profile.id} value={profile.id}>
                            {profile.name}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </Field>

                    <Field>
                      <FieldLabel>Command</FieldLabel>
                      <NativeSelect
                        className="task-form__select"
                        value={item.command_id}
                        onChange={(event) => updateItem(index, { command_id: event.target.value })}
                        disabled={fixedStage}
                      >
                        <NativeSelectOption value="">No default command</NativeSelectOption>
                        {commands.map((command) => (
                          <NativeSelectOption key={command.id} value={command.id}>
                            {command.name} ({command.slash_alias})
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </Field>
                  </div>

                  <Field orientation="horizontal" className="board-stage-editor__toggle">
                    <Checkbox
                      className="board-stage-editor__checkbox"
                      checked={item.auto_start}
                      onCheckedChange={(checked) => updateItem(index, { auto_start: checked === true })}
                      disabled={fixedStage}
                    />
                    <FieldLabel>
                    Auto-start when a task enters this stage
                    </FieldLabel>
                  </Field>
                </FieldGroup>

                <Button
                  type="button"
                  variant="ghost"
                  className="task-form__action-button board-stage-editor__remove-button"
                  onClick={() => removeStage(index)}
                  disabled={isSaving || items.length === 1 || fixedStage}
                >
                  <Trash2Icon data-icon="inline-start" />
                  Remove
                </Button>
                </div>
              );
            })}
          </div>

          {error ? (
            <Alert variant="destructive" className="settings-error-banner">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <DialogFooter className="board-stage-editor__actions">
            <Button
              type="button"
              variant="outline"
              className="task-form__action-button"
              onClick={addStage}
              disabled={isSaving}
            >
              <PlusIcon data-icon="inline-start" />
              Add Stage
            </Button>
            <Button
              type="submit"
              variant="default"
              className="task-form__action-button"
              disabled={isSaving}
            >
              {isSaving ? "Saving..." : "Save Board"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
