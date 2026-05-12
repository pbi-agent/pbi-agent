import type { ComponentType } from "react";
import type { LucideProps } from "lucide-react";
import { MarkdownContent } from "../shared/MarkdownContent";
import { FormDialog } from "../ui/form-dialog";

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
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={title}
      description={path}
      icon={<Icon />}
      size="wide"
      contentClassName="settings-preview-dialog"
    >
      <div className="command-preview-dialog__scroll timeline-entry timeline-entry--assistant">
        <div className="timeline-entry__content command-preview-dialog__markdown">
          <MarkdownContent content={content} />
        </div>
      </div>
    </FormDialog>
  );
}
