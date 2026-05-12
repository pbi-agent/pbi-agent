import type { ComponentProps, FormEvent } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SparklesIcon } from "lucide-react";
import { vi } from "vitest";
import { FormDialog } from "./form-dialog";

function renderFormDialog(overrides: Partial<ComponentProps<typeof FormDialog>> = {}) {
  const props: ComponentProps<typeof FormDialog> = {
    open: true,
    onOpenChange: vi.fn(),
    title: "Edit profile",
    description: "Update the profile settings.",
    icon: <SparklesIcon />,
    onSubmit: vi.fn((event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
    }),
    primaryAction: { label: "Save", pendingLabel: "Saving…" },
    onCancel: vi.fn(),
    children: <input aria-label="Name" />,
    ...overrides,
  };
  render(<FormDialog {...props} />);
  return props;
}

describe("FormDialog", () => {
  it("renders title, description, icon, body, and shadcn footer buttons", () => {
    renderFormDialog();

    expect(screen.getByRole("dialog", { name: "Edit profile" })).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Edit profile" })).toHaveClass("task-form-dialog");
    expect(screen.getByRole("dialog", { name: "Edit profile" })).toHaveAttribute("data-size", "md");
    expect(screen.getByText("Update the profile settings.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Name" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save" }).closest('[data-slot="dialog-footer"]'),
    ).toHaveClass("app-action-row", "app-action-row--end");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveAttribute("data-variant", "outline");
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("data-variant", "default");
  });

  it("submits through the form", async () => {
    const onSubmit = vi.fn((event: FormEvent<HTMLFormElement>) => event.preventDefault());
    renderFormDialog({ onSubmit });

    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), "x{enter}");
    expect(onSubmit).toHaveBeenCalled();
  });

  it("shows pending and error states", () => {
    renderFormDialog({ isPending: true, error: "Save failed" });

    expect(screen.getByRole("alert")).toHaveTextContent("Save failed");
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  });

  it("hides the footer when no primary action is provided", () => {
    renderFormDialog({ primaryAction: undefined, onSubmit: undefined });

    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("can hide the dialog close button while preserving the default", () => {
    renderFormDialog();
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();

    cleanup();
    renderFormDialog({ showCloseButton: false });
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  });
});
