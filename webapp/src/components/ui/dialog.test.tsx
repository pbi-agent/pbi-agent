import { render, screen } from "@testing-library/react";
import { Button } from "./button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./dialog";

function ActionDialog() {
  return (
    <Dialog open>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Save changes?</DialogTitle>
        </DialogHeader>
        <DialogFooter className="app-action-row app-action-row--end">
          <Button variant="outline">Cancel</Button>
          <Button>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

describe("Dialog", () => {
  it("keeps footer button spacing on the shared action row contract", () => {
    render(<ActionDialog />);

    const dialog = screen.getByRole("dialog", { name: "Save changes?" });
    const footer = dialog.querySelector('[data-slot="dialog-footer"]');

    expect(footer).toHaveClass("app-action-row", "app-action-row--end");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveAttribute(
      "data-variant",
      "outline",
    );
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute(
      "data-variant",
      "default",
    );
  });
});
