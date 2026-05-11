import type { SessionRecord } from "../../types";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

export function DeleteSessionModal({
  session,
  isDeleting,
  error,
  onConfirm,
  onClose,
}: {
  session: SessionRecord;
  isDeleting: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const title = session.title || "Untitled session";

  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => {
        if (!open && !isDeleting) onClose();
      }}
      title="Delete session?"
      description={
        <>
          This will permanently delete <strong>{title}</strong> and all of its
          saved messages.
        </>
      }
      confirmLabel="Delete session"
      pendingLabel="Deleting..."
      onConfirm={onConfirm}
      isPending={isDeleting}
      error={error}
    />
  );
}
