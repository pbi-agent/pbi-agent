import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { DeleteConfirmModal } from "./DeleteConfirmModal";

function renderDeleteConfirmModal(onConfirm = vi.fn().mockResolvedValue(undefined)) {
  render(
    <DeleteConfirmModal
      title="Delete Task"
      body={
        <>
          Delete task <strong>test OCR</strong>? This cannot be undone.
        </>
      }
      onConfirm={onConfirm}
      onClose={vi.fn()}
    />,
  );
}

describe("DeleteConfirmModal", () => {
  it("applies hover styling hooks to dialog actions", () => {
    renderDeleteConfirmModal();

    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(cancel).toHaveAttribute("data-variant", "outline");
    expect(cancel).toHaveClass("delete-confirm-modal__cancel");

    const action = screen.getByRole("button", { name: "Delete" });
    expect(action).toHaveAttribute("data-variant", "destructive");
    expect(action).toHaveClass("delete-confirm-modal__confirm");
  });

  it("disables the confirmation action while delete is pending", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn(() => new Promise<void>(() => {}));
    renderDeleteConfirmModal(onConfirm);

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Deleting…" })).toBeDisabled();
  });
});
