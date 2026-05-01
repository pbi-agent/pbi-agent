import {
  type ChangeEvent,
  type ClipboardEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
} from "react";
import { ImageIcon, XIcon } from "lucide-react";
import type { BoardStage, ImageAttachment, ModelProfileView } from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
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

export type PendingTaskImage = {
  id: string;
  file: File;
  previewUrl: string;
};

export type EditableTask = {
  taskId?: string;
  title: string;
  prompt: string;
  stage: string;
  projectDir: string;
  sessionId: string;
  profileId: string;
  imageAttachments: ImageAttachment[];
  imageFiles: PendingTaskImage[];
  imageError?: string | null;
};

const SUPPORTED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

type ImageFileInput = HTMLInputElement & {
  showPicker?: () => void;
};

function imageFingerprint(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function formatBytes(byteCount: number): string {
  return `${Math.max(1, Math.round(byteCount / 1024))} KB`;
}

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
  const imageInputRef = useRef<ImageFileInput>(null);
  const pendingImagesRef = useRef<PendingTaskImage[]>(task.imageFiles);
  const selectedProfile = task.profileId
    ? profiles.find((profile) => profile.id === task.profileId)
    : null;
  const selectedProfileDoesNotSupportImages =
    Boolean(selectedProfile) && !selectedProfile?.resolved_runtime.supports_image_inputs;
  const hasImages = task.imageAttachments.length > 0 || task.imageFiles.length > 0;

  useEffect(() => {
    pendingImagesRef.current = task.imageFiles;
  }, [task.imageFiles]);

  useEffect(() => {
    return () => {
      for (const image of pendingImagesRef.current) {
        URL.revokeObjectURL(image.previewUrl);
      }
    };
  }, []);

  const appendFiles = useCallback(
    (files: File[]) => {
      const supportedFiles = files.filter((file) => SUPPORTED_IMAGE_TYPES.has(file.type));
      if (supportedFiles.length === 0) {
        onChange({ imageError: "Only PNG, JPEG, and WEBP images are supported." });
        return;
      }
      const existing = new Set([
        ...task.imageFiles.map((image) => imageFingerprint(image.file)),
        ...task.imageAttachments.map(
          (attachment) => `${attachment.name}:${attachment.byte_count}`,
        ),
      ]);
      const additions = supportedFiles
        .filter((file) => {
          const fingerprint = imageFingerprint(file);
          if (existing.has(fingerprint)) return false;
          existing.add(fingerprint);
          return true;
        })
        .map((file) => ({
          id: `task-image-${crypto.randomUUID()}`,
          file,
          previewUrl: URL.createObjectURL(file),
        }));
      if (additions.length === 0) {
        onChange({ imageError: null });
        return;
      }
      onChange({
        imageFiles: [...task.imageFiles, ...additions],
        imageError: null,
      });
    },
    [onChange, task.imageAttachments, task.imageFiles],
  );

  const handleImageInput = (event: ChangeEvent<HTMLInputElement>) => {
    appendFiles(event.target.files ? Array.from(event.target.files) : []);
    event.target.value = "";
  };

  const handlePromptPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null);

    if (files.length === 0) return;

    event.preventDefault();
    appendFiles(files);
  };

  const openImagePicker = () => {
    const input = imageInputRef.current;
    if (!input || isSaving) return;
    if (typeof input.showPicker === "function") {
      input.showPicker();
      return;
    }
    input.click();
  };

  const removeExistingImage = (uploadId: string) => {
    onChange({
      imageAttachments: task.imageAttachments.filter(
        (attachment) => attachment.upload_id !== uploadId,
      ),
      imageError: null,
    });
  };

  const removePendingImage = (imageId: string) => {
    const target = task.imageFiles.find((image) => image.id === imageId);
    if (target) URL.revokeObjectURL(target.previewUrl);
    onChange({
      imageFiles: task.imageFiles.filter((image) => image.id !== imageId),
      imageError: null,
    });
  };

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
          <input
            ref={imageInputRef}
            type="file"
            name="task-image-upload"
            accept="image/png,image/jpeg,image/webp"
            multiple
            hidden
            onChange={handleImageInput}
          />
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
                  onPaste={handlePromptPaste}
                  required
                />
              </Field>

              <Field>
                <FieldLabel>Image attachments</FieldLabel>
                <div className="task-form__attachment-actions">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={openImagePicker}
                    disabled={isSaving}
                  >
                    <ImageIcon data-icon="inline-start" />
                    Add images
                  </Button>
                  <span className="task-form__attachment-note">
                    PNG, JPEG, or WEBP. Paste screenshots into the prompt or add files here.
                    Sent with the task prompt on the first run.
                  </span>
                </div>
                {hasImages ? (
                  <div className="task-form__attachments" aria-label="Task image attachments">
                    {task.imageAttachments.map((attachment) => (
                      <div key={attachment.upload_id} className="task-form__attachment-card">
                        <img
                          src={attachment.preview_url}
                          alt={attachment.name}
                          className="task-form__attachment-preview"
                        />
                        <div className="task-form__attachment-copy">
                          <span className="task-form__attachment-name" title={attachment.name}>
                            {attachment.name}
                          </span>
                          <span className="task-form__attachment-meta">
                            {formatBytes(attachment.byte_count)}
                          </span>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => removeExistingImage(attachment.upload_id)}
                          aria-label={`Remove ${attachment.name}`}
                          disabled={isSaving}
                        >
                          <XIcon aria-hidden="true" />
                        </Button>
                      </div>
                    ))}
                    {task.imageFiles.map((image) => (
                      <div key={image.id} className="task-form__attachment-card">
                        <img
                          src={image.previewUrl}
                          alt={image.file.name}
                          className="task-form__attachment-preview"
                        />
                        <div className="task-form__attachment-copy">
                          <span className="task-form__attachment-name" title={image.file.name}>
                            {image.file.name}
                          </span>
                          <span className="task-form__attachment-meta">
                            {formatBytes(image.file.size)} pending
                          </span>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => removePendingImage(image.id)}
                          aria-label={`Remove ${image.file.name}`}
                          disabled={isSaving}
                        >
                          <XIcon aria-hidden="true" />
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : null}
                {task.imageError ? (
                  <p className="task-form__error" role="alert">{task.imageError}</p>
                ) : null}
                {selectedProfileDoesNotSupportImages && hasImages ? (
                  <Alert variant="destructive">
                    <AlertDescription>
                      The selected profile runtime does not support image inputs. Remove the images or choose a different profile before running this task.
                    </AlertDescription>
                  </Alert>
                ) : null}
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
              variant="outline"
              className="task-form__action-button"
              onClick={onClose}
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="default"
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
