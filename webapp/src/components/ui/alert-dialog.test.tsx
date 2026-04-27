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
          <AlertDialogCancel variant="outline">Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive">Delete</AlertDialogAction>
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

    const action = screen.getByRole("button", { name: "Delete" });
    expect(action).toHaveAttribute("data-slot", "alert-dialog-action");
    expect(action).toHaveAttribute("data-variant", "destructive");
    expect(action).toHaveClass("bg-destructive/10", "text-destructive");
  });
});
