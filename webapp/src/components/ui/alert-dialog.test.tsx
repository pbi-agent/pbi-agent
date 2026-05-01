import { render, screen } from "@testing-library/react";
import { Trash2Icon } from "lucide-react";
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
} from "./alert-dialog";

function DestructiveAlertDialog() {
  return (
    <AlertDialog open>
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogMedia className="bg-destructive/10 text-destructive dark:bg-destructive/20 dark:text-destructive">
            <Trash2Icon />
          </AlertDialogMedia>
          <AlertDialogTitle>Delete chat?</AlertDialogTitle>
          <AlertDialogDescription>
            This will permanently delete this chat conversation.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="delete-confirm-modal__cancel" variant="outline">
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            className="delete-confirm-modal__confirm"
            variant="destructive"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

describe("AlertDialog", () => {
  it("applies destructive variants to destructive dialogs", () => {
    render(<DestructiveAlertDialog />);

    const dialog = screen.getByRole("alertdialog", { name: "Delete chat?" });
    expect(dialog).toHaveAttribute("data-size", "sm");

    const media = dialog.querySelector('[data-slot="alert-dialog-media"]');
    expect(media).toHaveClass(
      "bg-destructive/10",
      "text-destructive",
      "dark:bg-destructive/20",
      "dark:text-destructive",
    );

    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(cancel).toHaveAttribute("data-variant", "outline");

    const footer = dialog.querySelector('[data-slot="alert-dialog-footer"]');
    expect(footer).toHaveClass(
      "gap-2",
      "group-data-[size=sm]/alert-dialog-content:grid",
      "group-data-[size=sm]/alert-dialog-content:grid-cols-2",
    );
    expect(footer).not.toHaveClass("app-action-row");

    const action = screen.getByRole("button", { name: "Delete" });
    expect(action).toHaveAttribute("data-slot", "alert-dialog-action");
    expect(action).toHaveAttribute("data-variant", "destructive");
    expect(action).toHaveClass(
      "bg-destructive/10",
      "text-destructive",
      "delete-confirm-modal__confirm",
    );
  });
});
