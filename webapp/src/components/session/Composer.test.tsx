import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { Composer } from "./Composer";
import { renderWithProviders } from "../../test/render";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    searchFileMentions: vi.fn(),
    searchSlashCommands: vi.fn(),
  };
});

function renderComposer(
  overrides: Partial<React.ComponentProps<typeof Composer>> = {},
) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  renderWithProviders(
    <Composer
      inputEnabled
      sessionEnded={false}
      liveSessionId="live-1"
      supportsImageInputs
      isSubmitting={false}
      onSubmit={onSubmit}
      {...overrides}
    />,
  );
  return { onSubmit };
}

function renderSubmittingComposer() {
  let resolveSubmit: (() => void) | null = null;
  type SubmitPayload = { text: string; images: File[] };
  const onSubmit: ReturnType<typeof vi.fn<(payload: SubmitPayload) => Promise<void>>> =
    vi.fn(
      () => new Promise<void>((resolve) => {
        resolveSubmit = resolve;
      }),
    );

  function Harness() {
    const [isSubmitting, setIsSubmitting] = useState(false);
    return (
      <Composer
        inputEnabled
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        isSubmitting={isSubmitting}
        onSubmit={async (payload) => {
          setIsSubmitting(true);
          try {
            await onSubmit(payload);
          } finally {
            setIsSubmitting(false);
          }
        }}
      />
    );
  }

  renderWithProviders(<Harness />);
  return {
    onSubmit,
    resolveSubmit: () => resolveSubmit?.(),
  };
}

describe("Composer", () => {
  it("shows shell command affordances while typing a bang-prefixed input", async () => {
    const user = userEvent.setup();
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "!ls -la");

    expect(screen.getByLabelText("Shell command mode")).toBeInTheDocument();
    expect(
      screen.getByText("Enter will run this command in the workspace shell."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Actions" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Actions" })).toHaveAttribute(
      "title",
      "Images cannot be attached to shell commands",
    );
    expect(screen.getByPlaceholderText("Run a shell command...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run command" })).toHaveAttribute(
      "title",
      "Run command (Enter)",
    );
  });

  it("shows an empty shell command hint immediately after typing bang", async () => {
    const user = userEvent.setup();
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "!");

    expect(
      screen.getByText("Shell command mode: type a command after !"),
    ).toBeInTheDocument();
  });

  it("submits bang-prefixed input as trimmed text", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "!pwd{enter}");

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({ text: "!pwd", images: [] });
  });

  it("refocuses the message input after a submitted command completes", async () => {
    const user = userEvent.setup();
    const { onSubmit, resolveSubmit } = renderSubmittingComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "!pwd{enter}");

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("textbox", { name: "Message" })).toBeDisabled();

    resolveSubmit();

    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Message" })).toHaveFocus();
    });
  });
});