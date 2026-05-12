import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { SessionRecord } from "../../types";
import { DeleteSessionModal } from "./DeleteSessionModal";

const session: SessionRecord = {
  session_id: "session-1",
  directory: "/workspace",
  provider: "openai",
  provider_id: null,
  model: "gpt-4.1",
  profile_id: null,
  previous_id: null,
  title: "Plan margin fix",
  total_tokens: 0,
  input_tokens: 0,
  output_tokens: 0,
  cost_usd: 0,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

describe("DeleteSessionModal", () => {
  it("uses the shared delete dialog button styling without overriding the sm grid footer", () => {
    render(
      <DeleteSessionModal
        session={session}
        isDeleting={false}
        error={null}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const footer = screen
      .getByRole("alertdialog", { name: "Delete session?" })
      .querySelector('[data-slot="alert-dialog-footer"]');
    expect(footer).toHaveClass(
      "gap-2",
      "group-data-[size=sm]/alert-dialog-content:grid",
      "group-data-[size=sm]/alert-dialog-content:grid-cols-2",
    );
    expect(footer).not.toHaveClass("app-action-row");

    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(cancel).toHaveAttribute("data-variant", "outline");
    expect(cancel).toHaveClass("alert-dialog__button");

    const action = screen.getByRole("button", { name: "Delete session" });
    expect(action).toHaveAttribute("data-variant", "destructive");
    expect(action).toHaveClass("alert-dialog__button");
  });
});
