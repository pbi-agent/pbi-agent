import type { ComponentType } from "react";
import type { LucideProps } from "lucide-react";
import { MarkdownContent } from "../shared/MarkdownContent";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

type SettingsPreviewDialogProps = {
  title: string;
  path: string;
  content: string;
  icon: ComponentType<LucideProps>;
  onClose: () => void;
};

export function SettingsPreviewDialog({
  title,
  path,
  content,
  icon: Icon,
  onClose,
}: SettingsPreviewDialogProps) {
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="command-preview-dialog" aria-describedby={undefined}>
        <DialogHeader className="command-preview-dialog__header">
          <div className="command-preview-dialog__title-row">
            <div
              className="settings-command-icon settings-command-icon--dialog"
              aria-hidden="true"
            >
              <Icon />
            </div>
            <DialogTitle>{title}</DialogTitle>
            <span className="flex-1" />
            <span className="provider-card__subtitle">{path}</span>
          </div>
        </DialogHeader>
        <div className="command-preview-dialog__scroll timeline-entry timeline-entry--assistant">
          <div className="timeline-entry__content command-preview-dialog__markdown">
            <MarkdownContent content={content} />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
