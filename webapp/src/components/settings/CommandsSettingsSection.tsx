import { useState } from "react";
import { EyeIcon, FileTextIcon } from "lucide-react";
import type { CommandView } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { MarkdownContent } from "../shared/MarkdownContent";
import { Alert, AlertDescription } from "../ui/alert";
import { Card, CardContent } from "../ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

function CommandCard({
  command,
  onPreview,
}: {
  command: CommandView;
  onPreview: () => void;
}) {
  return (
    <Card className="settings-item settings-item--provider provider-card" role="button" tabIndex={0} onClick={onPreview} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPreview(); } }}>
      <div className="provider-card__info">
        <span className="settings-item__name">{command.name}</span>
        <div className="provider-card__subtitle">
          {command.slash_alias} · {command.description || command.path}
        </div>
      </div>
      <EyeIcon className="command-card__view-icon" />
    </Card>
  );
}

function CommandPreviewDialog({
  command,
  onClose,
}: {
  command: CommandView;
  onClose: () => void;
}) {
  return (
    <Dialog open onOpenChange={(open) => {
      if (!open) onClose();
    }}>
      <DialogContent className="command-preview-dialog" aria-describedby={undefined}>
        <DialogHeader className="command-preview-dialog__header">
          <div className="command-preview-dialog__title-row">
            <div className="settings-command-icon settings-command-icon--dialog" aria-hidden="true">
              <FileTextIcon />
            </div>
            <DialogTitle>{command.name}</DialogTitle>
            <span className="flex-1" />
            <span className="provider-card__subtitle">{command.path}</span>
          </div>
        </DialogHeader>
        <div className="command-preview-dialog__scroll timeline-entry timeline-entry--assistant">
          <div className="timeline-entry__content command-preview-dialog__markdown">
            <MarkdownContent content={command.instructions} />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function CommandsSettingsSection({ commands }: { commands: CommandView[] }) {
  const [previewCommand, setPreviewCommand] = useState<CommandView | null>(null);

  return (
    <section className="settings-section settings-section--active">
      <Alert className="settings-inline-note commands-hint">
        <AlertDescription>
          Add Markdown files under <code className="command-hint__path">.agents/commands/</code> — a file
          like <code className="command-hint__path">.agents/commands/review.md</code> becomes <code className="command-hint__path">/review</code>.
        </AlertDescription>
      </Alert>
      <Card className="settings-panel">
        <CardContent className="settings-panel__body">
          {commands.length === 0 ? (
            <EmptyState title="No commands found" description="Add project command files under .agents/commands/." />
          ) : (
            commands.map((command) => (
              <CommandCard
                key={command.id}
                command={command}
                onPreview={() => setPreviewCommand(command)}
              />
            ))
          )}
        </CardContent>
      </Card>
      {previewCommand && (
        <CommandPreviewDialog
          command={previewCommand}
          onClose={() => setPreviewCommand(null)}
        />
      )}
    </section>
  );
}
