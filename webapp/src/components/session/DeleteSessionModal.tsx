import { Trash2Icon } from "lucide-react";
import type { SessionRecord } from "../../types";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";

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
    <AlertDialog open onOpenChange={(open) => {
      if (!open && !isDeleting) onClose();
    }}>
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogMedia className="bg-destructive/10 text-destructive dark:bg-destructive/20 dark:text-destructive">
            <Trash2Icon />
          </AlertDialogMedia>
          <AlertDialogTitle>Delete session?</AlertDialogTitle>
          <AlertDialogDescription>
            This will permanently delete <strong>{title}</strong> and all of its
            saved messages.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <AlertDialogFooter>
          <AlertDialogCancel
            className="delete-confirm-modal__cancel"
            onClick={onClose}
            disabled={isDeleting}
          >
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            className="delete-confirm-modal__confirm"
            onClick={onConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? "Deleting..." : "Delete session"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
