import userEvent from "@testing-library/user-event";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { Composer } from "./Composer";
import { searchFileMentions, searchSkillMentions, searchSlashCommands } from "../../api";
import { renderWithProviders } from "../../test/render";
import { resetFileExistenceForTest } from "../../hooks/useFileExistence";
import { resetSkillCatalogForTest } from "../../hooks/useSkillCatalog";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    searchFileMentions: vi.fn(),
    searchSkillMentions: vi.fn(),
    searchSlashCommands: vi.fn(),
  };
});

function renderComposer(
  overrides: Partial<React.ComponentProps<typeof Composer>> = {},
) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const renderResult = renderWithProviders(
    <Composer
      inputEnabled
      sessionEnded={false}
      liveSessionId="live-1"
      supportsImageInputs
      interactiveMode={false}
      isSubmitting={false}
      onSubmit={onSubmit}
      {...overrides}
    />,
  );
  return { onSubmit, ...renderResult };
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
        interactiveMode={false}
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

type InputPrototypeWithPicker = typeof HTMLInputElement.prototype & {
  showPicker: (() => void) | undefined;
};

const inputPrototype: InputPrototypeWithPicker = HTMLInputElement.prototype;

describe("Composer", () => {
  beforeEach(() => {
    resetFileExistenceForTest();
    resetSkillCatalogForTest();
    vi.useRealTimers();
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 0;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    if (!URL.createObjectURL) {
      URL.createObjectURL = () => "blob:preview";
    }
    if (!URL.revokeObjectURL) {
      URL.revokeObjectURL = () => undefined;
    }
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [],
      scan_status: "ready",
      is_stale: false,
      file_count: 0,
      error: null,
    });
    vi.mocked(searchSkillMentions).mockResolvedValue({ items: [] });
    vi.mocked(searchSlashCommands).mockResolvedValue([]);
  });

  it("opens the native image picker from the actions menu", async () => {
    const user = userEvent.setup();
    const showPicker = vi.fn();
    const originalShowPicker = inputPrototype.showPicker;
    inputPrototype.showPicker = showPicker;

    try {
      renderComposer();

      await user.click(screen.getByRole("button", { name: "Actions" }));
      await user.click(screen.getByRole("menuitem", { name: "Image" }));

      await waitFor(() => expect(showPicker).toHaveBeenCalledTimes(1));
    } finally {
      if (originalShowPicker) {
        inputPrototype.showPicker = originalShowPicker;
      } else {
        Reflect.deleteProperty(inputPrototype, "showPicker");
      }
    }
  });

  it("highlights file and skill tags inside the message input only after validation", async () => {
    vi.mocked(searchSkillMentions).mockResolvedValue({
      items: [{ name: "compress", description: "Compress", path: ".agents/skills/compress/SKILL.md" }],
    });
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [{ path: "src/main.py", kind: "file" }],
      scan_status: "ready",
      is_stale: false,
      file_count: 1,
      error: null,
    });
    const user = userEvent.setup();
    const { container } = renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "Use @src/main.py with $compress");

    await waitFor(() => {
      expect(container.querySelector(".composer__textarea-highlight--skill")).toHaveTextContent(
        "$compress",
      );
    });
    await waitFor(() => {
      expect(container.querySelector(".composer__textarea-highlight--mention")).toHaveTextContent(
        "@src/main.py",
      );
    });
  });

  it("keeps unknown file and skill tags plain", async () => {
    vi.mocked(searchSkillMentions).mockResolvedValue({
      items: [{ name: "compress", description: "Compress", path: ".agents/skills/compress/SKILL.md" }],
    });
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [],
      scan_status: "ready",
      is_stale: false,
      file_count: 0,
      error: null,
    });
    const user = userEvent.setup();
    const { container } = renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "Use @made/up/path.py with $notaskill");

    await waitFor(() => expect(searchFileMentions).toHaveBeenCalled());
    expect(container.querySelector(".composer__textarea-highlight--mention")).not.toBeInTheDocument();
    expect(container.querySelector(".composer__textarea-highlight--skill")).not.toBeInTheDocument();
  });

  it("renders no highlight chips in shell mode", async () => {
    vi.mocked(searchSkillMentions).mockResolvedValue({
      items: [{ name: "HOME", description: "Home", path: ".agents/skills/HOME/SKILL.md" }],
    });
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [{ path: "src/x.py", kind: "file" }],
      scan_status: "ready",
      is_stale: false,
      file_count: 1,
      error: null,
    });
    const user = userEvent.setup();
    const { container } = renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "!ls $HOME @src/x.py");

    expect(container.querySelector(".composer__textarea-highlight")).not.toBeInTheDocument();
    expect(searchFileMentions).not.toHaveBeenCalledWith("src/x.py", expect.anything(), expect.anything());
  });

  it("enables message and image controls for lazy-created sessions", () => {
    renderComposer({
      liveSessionId: null,
      canCreateSession: true,
    });

    expect(screen.getByRole("textbox", { name: "Message" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Actions" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
  });

  it("marks the input row while interactive mode is enabled", () => {
    renderComposer({ interactiveMode: true });

    const inputRow = screen.getByRole("textbox", { name: "Message" }).closest(".composer__input-row");
    expect(inputRow).toHaveClass("composer__input-row--interactive");
  });

  it("recalls the latest input history item with ArrowUp in an empty focused textbox", () => {
    renderComposer({ inputHistory: ["first request", "latest request"] });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    textbox.focus();
    fireEvent.keyDown(textbox, { key: "ArrowUp" });

    expect(textbox).toHaveValue("latest request");
    expect((textbox as HTMLTextAreaElement).selectionStart).toBe("latest request".length);
    expect((textbox as HTMLTextAreaElement).selectionEnd).toBe("latest request".length);
  });

  it("walks older history with repeated ArrowUp and stops at the oldest input", () => {
    renderComposer({ inputHistory: ["oldest", "middle", "latest"] });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    textbox.focus();
    fireEvent.keyDown(textbox, { key: "ArrowUp" });
    expect(textbox).toHaveValue("latest");
    fireEvent.keyDown(textbox, { key: "ArrowUp" });
    expect(textbox).toHaveValue("middle");
    fireEvent.keyDown(textbox, { key: "ArrowUp" });
    expect(textbox).toHaveValue("oldest");
    fireEvent.keyDown(textbox, { key: "ArrowUp" });
    expect(textbox).toHaveValue("oldest");
  });

  it("moves newer with ArrowDown and restores the pre-history draft", async () => {
    const user = userEvent.setup();
    renderComposer({ inputHistory: ["oldest", "latest"] });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    await user.type(textbox, "draft text");
    fireEvent.keyDown(textbox, { key: "ArrowUp" });
    expect(textbox).toHaveValue("latest");
    fireEvent.keyDown(textbox, { key: "ArrowUp" });
    expect(textbox).toHaveValue("oldest");
    fireEvent.keyDown(textbox, { key: "ArrowDown" });
    expect(textbox).toHaveValue("latest");
    fireEvent.keyDown(textbox, { key: "ArrowDown" });
    expect(textbox).toHaveValue("draft text");
  });

  it("restores the draft and exits history browsing when input history changes", async () => {
    const user = userEvent.setup();
    const { onSubmit, rerender } = renderComposer({ inputHistory: ["old history"] });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    await user.type(textbox, "draft text");
    fireEvent.keyDown(textbox, { key: "ArrowUp" });
    expect(textbox).toHaveValue("old history");

    rerender(
      <Composer
        inputEnabled
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        onSubmit={onSubmit}
        inputHistory={["different history"]}
      />,
    );

    await waitFor(() => expect(textbox).toHaveValue("draft text"));
    fireEvent.keyDown(textbox, { key: "ArrowDown" });
    expect(textbox).toHaveValue("draft text");
  });

  it("keeps ArrowUp reserved for completion navigation when suggestions are open", async () => {
    const user = userEvent.setup();
    vi.mocked(searchSkillMentions).mockResolvedValue({
      items: [{ name: "writer", description: "Write prose", path: ".agents/skills/writer/SKILL.md" }],
    });
    renderComposer({ inputHistory: ["latest request"] });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    await user.type(textbox, "$w");
    expect(await screen.findByRole("listbox", { name: "Skill suggestions" })).toBeInTheDocument();
    fireEvent.keyDown(textbox, { key: "ArrowUp" });

    expect(textbox).toHaveValue("$w");
  });

  it("does not override normal multiline ArrowUp navigation below the first line", () => {
    renderComposer({ inputHistory: ["latest request"] });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    fireEvent.change(textbox, {
      target: {
        value: "first line\nsecond line",
        selectionStart: "first line\nsecond line".length,
      },
    });
    fireEvent.keyDown(textbox, { key: "ArrowUp" });

    expect(textbox).toHaveValue("first line\nsecond line");
  });

  it("does not open the image picker when image inputs are unsupported", async () => {
    const user = userEvent.setup();
    const showPicker = vi.fn();
    const originalShowPicker = inputPrototype.showPicker;
    inputPrototype.showPicker = showPicker;

    try {
      renderComposer({ supportsImageInputs: false });

      await user.click(screen.getByRole("button", { name: "Actions" }));

      expect(screen.getByRole("menuitem", { name: "Image" })).toHaveAttribute(
        "aria-disabled",
        "true",
      );
      expect(showPicker).not.toHaveBeenCalled();
    } finally {
      if (originalShowPicker) {
        inputPrototype.showPicker = originalShowPicker;
      } else {
        Reflect.deleteProperty(inputPrototype, "showPicker");
      }
    }
  });

  it("submits selected image files with the message", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer();
    const image = new File(["binary"], "diagram.png", { type: "image/png" });

    await user.upload(document.querySelector('input[name="image-upload"]')!, image);
    expect(screen.getByText("diagram.png")).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "review this");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({ text: "review this", images: [image] });
  });

  it("shows shell command affordances while typing a bang-prefixed input", async () => {
    const user = userEvent.setup();
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "!ls -la");

    function hasAppTooltip(text: string) {
      return Array.from(document.querySelectorAll("[data-app-tooltip]")).some(
        (node) => node.textContent?.includes(text),
      );
    }

    expect(screen.getByLabelText("Shell command mode")).toBeInTheDocument();
    expect(
      screen.getByText("Enter will run this command in the workspace shell."),
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Run a shell command...")).toBeInTheDocument();
    const runButton = screen.getByRole("button", { name: "Run command" });
    expect(runButton).not.toHaveAttribute("title");

    const actionsButton = screen.getByRole("button", { name: "Actions" });
    expect(actionsButton).toBeDisabled();
    expect(actionsButton).not.toHaveAttribute("title");
    const actionsTooltipTrigger = actionsButton.closest(".composer__action-tooltip-trigger");
    expect(actionsTooltipTrigger).not.toBeNull();
    await user.hover(actionsTooltipTrigger!);
    await waitFor(() => {
      expect(hasAppTooltip("Images cannot be attached to shell commands")).toBe(true);
    });
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

  it("shows a processing rail when the composer is locked by an active turn", () => {
    const { container } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
    });

    expect(screen.getByRole("textbox", { name: "Message" })).toBeDisabled();
    expect(container.querySelector(".composer__input-row--processing")).toBeInTheDocument();
    expect(container.querySelector(".composer__processing-indicator")).not.toBeInTheDocument();
    expect(container.querySelector(".composer__processing-bar")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Assistant is processing");
  });

  it("restores interrupted input into the textbox", async () => {
    const onConsumed = vi.fn();
    renderComposer({
      inputEnabled: true,
      restoredInput: "restore this",
      onRestoredInputConsumed: onConsumed,
    });

    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("restore this");
    });
    expect(onConsumed).toHaveBeenCalledTimes(1);
  });

  it("polls cold file-index scans until file mention results are ready", async () => {
    const user = userEvent.setup();
    vi.mocked(searchFileMentions)
      .mockResolvedValueOnce({
        items: [],
        scan_status: "scanning",
        is_stale: false,
        file_count: 0,
        error: null,
      })
      .mockResolvedValueOnce({
        items: [{ path: "src/main.py", kind: "file" }],
        scan_status: "ready",
        is_stale: false,
        file_count: 1,
        error: null,
      });
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "@");

    expect(await screen.findByText("Indexing files...")).toBeInTheDocument();
    expect(await screen.findByText("@src/main.py", {}, { timeout: 2_000 })).toBeInTheDocument();
    expect(searchFileMentions).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Indexing files...")).not.toBeInTheDocument();
  });

  it("polls stale file-index refreshes while preserving items", async () => {
    const user = userEvent.setup();
    vi.mocked(searchFileMentions)
      .mockResolvedValueOnce({
        items: [{ path: "src/old.py", kind: "file" }],
        scan_status: "scanning",
        is_stale: true,
        file_count: 1,
        error: null,
      })
      .mockResolvedValueOnce({
        items: [{ path: "src/main.py", kind: "file" }],
        scan_status: "ready",
        is_stale: false,
        file_count: 1,
        error: null,
      });
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "@ma");

    expect(await screen.findByText("@src/old.py")).toBeInTheDocument();
    expect(screen.getByText("Refreshing file index...")).toBeInTheDocument();
    expect(await screen.findByText("@src/main.py", {}, { timeout: 2_000 })).toBeInTheDocument();
    expect(searchFileMentions).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Refreshing file index...")).not.toBeInTheDocument();
  });

  it("does not poll dismissed file mention completions", async () => {
    const user = userEvent.setup();
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [],
      scan_status: "scanning",
      is_stale: false,
      file_count: 0,
      error: null,
    });
    renderComposer();

    const textbox = screen.getByRole("textbox", { name: "Message" });
    await user.type(textbox, "@");
    expect(await screen.findByText("Indexing files...")).toBeInTheDocument();
    fireEvent.keyDown(textbox, { key: "Escape" });
    await new Promise((resolve) => window.setTimeout(resolve, 650));

    expect(searchFileMentions).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Indexing files...")).not.toBeInTheDocument();
  });

  it("shows scan failure messages", async () => {
    const user = userEvent.setup();
    vi.mocked(searchFileMentions).mockResolvedValueOnce({
      items: [],
      scan_status: "failed",
      is_stale: false,
      file_count: 0,
      error: "git failed",
    });
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "@");

    expect(await screen.findByText("git failed")).toBeInTheDocument();
  });

  it("discards older file completion responses", async () => {
    const user = userEvent.setup();
    let resolveFirst: ((value: Awaited<ReturnType<typeof searchFileMentions>>) => void) | undefined;
    vi.mocked(searchFileMentions)
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({
        items: [{ path: "beta.txt", kind: "file" }],
        scan_status: "ready",
        is_stale: false,
        file_count: 1,
        error: null,
      });
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "@a");
    await waitFor(() => expect(searchFileMentions).toHaveBeenCalledTimes(1));
    await user.type(screen.getByRole("textbox", { name: "Message" }), "b");
    if (!resolveFirst) {
      throw new Error("first search did not start");
    }
    resolveFirst({
      items: [{ path: "alpha.txt", kind: "file" }],
      scan_status: "ready",
      is_stale: false,
      file_count: 1,
      error: null,
    });

    expect(await screen.findByText("@beta.txt")).toBeInTheDocument();
    expect(screen.queryByText("@alpha.txt")).not.toBeInTheDocument();
  });

  it("parses token mentions without treating later at signs as new triggers", async () => {
    const user = userEvent.setup();
    vi.mocked(searchFileMentions).mockResolvedValueOnce({
      items: [{ path: "icons/icon@2x.png", kind: "image" }],
      scan_status: "ready",
      is_stale: false,
      file_count: 1,
      error: null,
    });
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "@icons/icon@2");

    expect(await screen.findByText("@icons/icon@2x.png")).toBeInTheDocument();
    expect(searchFileMentions).toHaveBeenLastCalledWith("icons/icon@2", 8);
  });

  it("does not open file completions for email or import-alias tokens", async () => {
    const user = userEvent.setup();
    renderComposer();
    const textbox = screen.getByRole("textbox", { name: "Message" });

    await user.type(textbox, "user@example.com");
    expect(screen.queryByRole("listbox", { name: "Workspace file suggestions" })).not.toBeInTheDocument();

    await user.clear(textbox);
    await user.type(textbox, "@/components");
    expect(screen.queryByRole("listbox", { name: "Workspace file suggestions" })).not.toBeInTheDocument();
  });

  it("opens and inserts skill tag completions", async () => {
    const user = userEvent.setup();
    vi.mocked(searchSkillMentions).mockResolvedValue({
      items: [
        {
          name: "release-writing",
          description: "Write release notes",
          path: ".agents/skills/release-writing/SKILL.md",
        },
      ],
    });
    renderComposer();

    const textbox = screen.getByRole("textbox", { name: "Message" });
    await user.type(textbox, "$rel");

    expect(await screen.findByRole("listbox", { name: "Skill suggestions" })).toBeInTheDocument();
    expect(await screen.findByText("$release-writing", { exact: false })).toHaveTextContent(
      "$release-writing (Write release notes)",
    );
    await user.keyboard("{Enter}");
    expect(textbox).toHaveValue("$release-writing ");
  });

  it("clicks skill tag completions", async () => {
    const user = userEvent.setup();
    vi.mocked(searchSkillMentions).mockResolvedValue({
      items: [
        {
          name: "shadcn",
          description: "Compose UI",
          path: ".agents/skills/shadcn/SKILL.md",
        },
      ],
    });
    renderComposer();

    const textbox = screen.getByRole("textbox", { name: "Message" });
    await user.type(textbox, "Use $sha");
    await user.click(await screen.findByText("$shadcn", { exact: false }));

    expect(textbox).toHaveValue("Use $shadcn ");
  });

  it("discards older skill completion responses", async () => {
    const user = userEvent.setup();
    let resolveFirst: ((value: Awaited<ReturnType<typeof searchSkillMentions>>) => void) | undefined;
    vi.mocked(searchSkillMentions)
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({
        items: [
          {
            name: "beta",
            description: "Second skill",
            path: ".agents/skills/beta/SKILL.md",
          },
        ],
      });
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "$a");
    await waitFor(() => expect(searchSkillMentions).toHaveBeenCalledTimes(1));
    await user.type(screen.getByRole("textbox", { name: "Message" }), "b");
    if (!resolveFirst) {
      throw new Error("first skill search did not start");
    }
    resolveFirst({
      items: [
        {
          name: "alpha",
          description: "First skill",
          path: ".agents/skills/alpha/SKILL.md",
        },
      ],
    });

    expect(await screen.findByText("$beta", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("$alpha", { exact: false })).not.toBeInTheDocument();
  });

  it("dismisses skill completions until the token changes", async () => {
    const user = userEvent.setup();
    vi.mocked(searchSkillMentions).mockResolvedValue({
      items: [
        {
          name: "writer",
          description: "Write prose",
          path: ".agents/skills/writer/SKILL.md",
        },
      ],
    });
    renderComposer();

    const textbox = screen.getByRole("textbox", { name: "Message" });
    await user.type(textbox, "$w");
    expect(await screen.findByRole("listbox", { name: "Skill suggestions" })).toBeInTheDocument();
    fireEvent.keyDown(textbox, { key: "Escape" });
    expect(screen.queryByRole("listbox", { name: "Skill suggestions" })).not.toBeInTheDocument();

    await user.type(textbox, "r");

    expect(await screen.findByRole("listbox", { name: "Skill suggestions" })).toBeInTheDocument();
  });

  it("does not open skill completions for shell variables or shell mode", async () => {
    const user = userEvent.setup();
    renderComposer();
    const textbox = screen.getByRole("textbox", { name: "Message" });

    await user.type(textbox, "echo $1 ${{foo}} $(pwd)");
    expect(screen.queryByRole("listbox", { name: "Skill suggestions" })).not.toBeInTheDocument();

    await user.clear(textbox);
    await user.type(textbox, "!echo $skill");
    expect(screen.queryByRole("listbox", { name: "Skill suggestions" })).not.toBeInTheDocument();
    expect(searchSkillMentions).toHaveBeenCalledWith("", 200);
    expect(searchSkillMentions).toHaveBeenCalledTimes(1);
  });

  it("renders slash command descriptions inline in parentheses", async () => {
    const user = userEvent.setup();
    vi.mocked(searchSlashCommands).mockResolvedValue([
      {
        name: "/plan",
        description: "Plan Mode Non-Interactive",
        kind: "local_command",
      },
    ]);
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "/");

    expect(
      await screen.findByRole("listbox", { name: "Slash command suggestions" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("/plan", { exact: false })).toHaveTextContent(
      "/plan (Plan Mode Non-Interactive)",
    );
  });
});
