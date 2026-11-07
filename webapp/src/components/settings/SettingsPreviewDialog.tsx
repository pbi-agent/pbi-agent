import type { ComponentType, ReactNode } from "react";
import type { LucideProps } from "lucide-react";
import { MarkdownContent } from "../shared/MarkdownContent";
import { FormDialog } from "../ui/form-dialog";

type SettingsPreviewDialogProps = {
  title: string;
  path: string;
  content: string;
  icon: ComponentType<LucideProps>;
  headerContent?: ReactNode;
  onClose: () => void;
};

export function SettingsPreviewDialog({
  title,
  path,
  content,
  icon: Icon,
  headerContent,
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
      headerContent={headerContent}
      icon={<Icon />}
      size="wide"
    >
      <div className="min-w-0 overflow-auto" data-settings-preview-content>
        <MarkdownContent content={content} />
      </div>
    </FormDialog>
  );
}
