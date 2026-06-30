import userEvent from "@testing-library/user-event";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { Composer } from "./Composer";
import { searchAgentMentions, searchFileMentions, searchSkillMentions, searchSlashCommands } from "../../api";
import { renderWithProviders } from "../../test/render";
import { resetFileExistenceForTest } from "../../hooks/useFileExistence";
import { resetSkillCatalogForTest } from "../../hooks/useSkillCatalog";

const createWavRecorderMock = vi.hoisted(() => vi.fn());
const recorderStopMock = vi.hoisted(() => vi.fn());
const recorderCancelMock = vi.hoisted(() => vi.fn());
const recorderFrequencyMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/audioRecorder", () => ({
  createWavRecorder: createWavRecorderMock,
}));

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    searchAgentMentions: vi.fn(),
    searchFileMentions: vi.fn(),
    searchSkillMentions: vi.fn(),
    searchSlashCommands: vi.fn(),
  };
});

function renderComposer(
  overrides: Partial<React.ComponentProps<typeof Composer>> = {},
) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const onTranscribeDictation = vi.fn().mockResolvedValue("transcribed text");
  const onEnhancePrompt = vi.fn().mockResolvedValue("enhanced prompt");
  const renderResult = renderWithProviders(
    <Composer
      inputEnabled
      sessionEnded={false}
      liveSessionId="live-1"
      supportsImageInputs
      interactiveMode={false}
      isSubmitting={false}
      onSubmit={onSubmit}
      dictationAvailable
      dictationUnavailableReason={null}
      onTranscribeDictation={onTranscribeDictation}
      onEnhancePrompt={onEnhancePrompt}
      {...overrides}
    />,
  );
  return { onSubmit, onTranscribeDictation, onEnhancePrompt, ...renderResult };
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
    createWavRecorderMock.mockReset();
    recorderStopMock.mockReset();
    recorderCancelMock.mockReset();
    recorderFrequencyMock.mockReset();
    recorderStopMock.mockResolvedValue(
      new File(["RIFF"], "dictation.wav", { type: "audio/wav" }),
    );
    recorderCancelMock.mockResolvedValue(undefined);
    recorderFrequencyMock.mockReturnValue(new Uint8Array(0));
    createWavRecorderMock.mockResolvedValue({
      stop: recorderStopMock,
      cancel: recorderCancelMock,
      getFrequencyData: recorderFrequencyMock,
    });
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [],
      scan_status: "ready",
      is_stale: false,
      file_count: 0,
      error: null,
    });
    vi.mocked(searchAgentMentions).mockResolvedValue({ items: [] });
    vi.mocked(searchSkillMentions).mockResolvedValue({ items: [] });
    vi.mocked(searchSlashCommands).mockResolvedValue([]);
  });

  it("opens the native image picker from the actions menu", async () => {
    const user = userEvent.setup();
    const showPicker = vi.fn();
    const originalShowPicker = inputPrototype.showPicker;
    inputPrototype.showPicker = showPicker;

    try {
      const { container } = renderComposer();
      const input = container.querySelector<HTMLInputElement>(
        'input[name="image-upload"]',
      );
      expect(input?.accept).toBe(
        "image/png,image/jpeg,image/webp,image/heic,image/heif,.heic,.heif",
      );

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
    expect(screen.getByRole("button", { name: "Start dictation" })).toBeEnabled();
  });

  it("shows dictation for an empty composer and send for non-empty text", async () => {
    const user = userEvent.setup();
    renderComposer();

    expect(screen.getByRole("button", { name: "Start dictation" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enhance prompt" })).not.toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "review this");

    expect(screen.getByRole("button", { name: "Enhance prompt" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start dictation" })).not.toBeInTheDocument();
  });

  it("keeps the mic for empty image attachments and does not submit image-only input", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer();
    const image = new File(["binary"], "diagram.png", { type: "image/png" });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    await user.upload(document.querySelector('input[name="image-upload"]')!, image);

    expect(screen.getByText("diagram.png")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start dictation" })).toBeInTheDocument();

    fireEvent.keyDown(textbox, { key: "Enter" });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("diagram.png")).toBeInTheDocument();
  });

  it("records, transcribes, inserts text without submitting, and preserves attachments", async () => {
    const user = userEvent.setup();
    let resolveTranscription: ((value: string) => void) | undefined;
    const onTranscribeDictation = vi.fn(
      () => new Promise<string>((resolve) => {
        resolveTranscription = resolve;
      }),
    );
    const { onSubmit } = renderComposer({ onTranscribeDictation });
    const image = new File(["binary"], "diagram.png", { type: "image/png" });

    await user.upload(document.querySelector('input[name="image-upload"]')!, image);
    await user.click(screen.getByRole("button", { name: "Start dictation" }));

    expect(await screen.findByRole("button", { name: "Stop dictation recording" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(createWavRecorderMock).toHaveBeenCalledTimes(1);

    expect(screen.queryByRole("textbox", { name: "Message" })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Recording audio/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Stop dictation recording" }));

    expect(screen.queryByRole("img", { name: /Recording audio/ })).not.toBeInTheDocument();

    expect(await screen.findByRole("button", { name: "Transcribing dictation" })).toBeDisabled();
    expect(recorderStopMock).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(onTranscribeDictation).toHaveBeenCalledTimes(1));
    act(() => {
      resolveTranscription?.("dictated request");
    });

    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("dictated request");
    });
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveFocus();
    expect(screen.getByText("diagram.png")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("toggles dictation with Ctrl+Space only while the composer is active", async () => {
    renderComposer();

    fireEvent.keyDown(document.body, { key: " ", code: "Space", ctrlKey: true });
    expect(createWavRecorderMock).not.toHaveBeenCalled();

    const textbox = screen.getByRole("textbox", { name: "Message" });
    textbox.focus();
    fireEvent.keyDown(textbox, { key: " ", code: "Space", ctrlKey: true });

    expect(await screen.findByRole("button", { name: "Stop dictation recording" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Message" })).not.toBeInTheDocument();

    fireEvent.keyDown(document.body, { key: " ", code: "Space", ctrlKey: true });

    await waitFor(() => expect(recorderStopMock).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("transcribed text");
    });
  });

  it("enhances non-empty prompt text with Ctrl+Space without submitting", async () => {
    const user = userEvent.setup();
    const onEnhancePrompt = vi.fn().mockResolvedValue("Please review this.");
    const { onSubmit } = renderComposer({ onEnhancePrompt });

    const textbox = screen.getByRole("textbox", { name: "Message" });
    await user.type(textbox, "please review ths");
    fireEvent.keyDown(textbox, { key: " ", code: "Space", ctrlKey: true });

    await waitFor(() => {
      expect(onEnhancePrompt).toHaveBeenCalledWith("please review ths");
    });
    await waitFor(() => {
      expect(textbox).toHaveValue("Please review this.");
    });
    expect(createWavRecorderMock).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("does not enhance empty, slash, or shell drafts with Ctrl+Space", async () => {
    const user = userEvent.setup();
    const onEnhancePrompt = vi.fn().mockResolvedValue("enhanced");
    renderComposer({ dictationAvailable: false, onEnhancePrompt });

    const textbox = screen.getByRole("textbox", { name: "Message" });
    textbox.focus();
    fireEvent.keyDown(textbox, { key: " ", code: "Space", ctrlKey: true });
    expect(onEnhancePrompt).not.toHaveBeenCalled();

    await user.type(textbox, "/plan");
    fireEvent.keyDown(textbox, { key: " ", code: "Space", ctrlKey: true });
    expect(onEnhancePrompt).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Enhance prompt" })).not.toBeInTheDocument();

    await user.clear(textbox);
    await user.type(textbox, "!pwd");
    fireEvent.keyDown(textbox, { key: " ", code: "Space", ctrlKey: true });
    expect(onEnhancePrompt).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Enhance prompt" })).not.toBeInTheDocument();
  });

  it("shows prompt enhancement loading and error states without changing the draft", async () => {
    const user = userEvent.setup();
    let resolveEnhancement: ((value: string) => void) | undefined;
    const onEnhancePrompt = vi.fn(
      () => new Promise<string>((resolve) => {
        resolveEnhancement = resolve;
      }),
    );
    const { rerender } = renderComposer({ onEnhancePrompt });

    const textbox = screen.getByRole("textbox", { name: "Message" });
    await user.type(textbox, "make this clearer");
    await user.click(screen.getByRole("button", { name: "Enhance prompt" }));

    expect(textbox).toBeDisabled();
    expect(textbox.closest(".composer__input-row")).toHaveClass(
      "composer__input-row--processing",
    );
    expect(screen.getByText("Enhancing prompt")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Actions" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Enhancing prompt" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();

    act(() => {
      resolveEnhancement?.("Make this clearer.");
    });
    await waitFor(() => {
      expect(textbox).toHaveValue("Make this clearer.");
    });
    await waitFor(() => expect(textbox).toBeEnabled());

    const rejectingEnhance = vi.fn().mockRejectedValue(new Error("Enhancement failed"));
    rerender(
      <Composer
        inputEnabled
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        dictationAvailable
        dictationUnavailableReason={null}
        onTranscribeDictation={vi.fn().mockResolvedValue("transcribed text")}
        onEnhancePrompt={rejectingEnhance}
      />,
    );
    const rerenderedTextbox = screen.getByRole("textbox", { name: "Message" });
    await user.clear(rerenderedTextbox);
    await user.type(rerenderedTextbox, "keep original");
    await user.click(screen.getByRole("button", { name: "Enhance prompt" }));

    expect(await screen.findByText("Enhancement failed")).toBeInTheDocument();
    expect(rerenderedTextbox).toHaveValue("keep original");
    expect(screen.getByRole("button", { name: "Enhance prompt" })).toBeEnabled();
  });

  it("handles Ctrl+Space once when focus stays on the dictation button", async () => {
    const user = userEvent.setup();
    let resolveTranscription: ((value: string) => void) | undefined;
    const onTranscribeDictation = vi.fn(
      () => new Promise<string>((resolve) => {
        resolveTranscription = resolve;
      }),
    );
    renderComposer({ onTranscribeDictation });

    await user.click(screen.getByRole("button", { name: "Start dictation" }));
    const stopButton = await screen.findByRole("button", {
      name: "Stop dictation recording",
    });
    expect(stopButton).toHaveFocus();

    fireEvent.keyDown(stopButton, { key: " ", code: "Space", ctrlKey: true });

    expect(await screen.findByRole("button", { name: "Transcribing dictation" })).toBeDisabled();
    expect(recorderStopMock).toHaveBeenCalledTimes(1);
    expect(onTranscribeDictation).toHaveBeenCalledTimes(1);

    act(() => {
      resolveTranscription?.("button focus transcript");
    });
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue(
        "button focus transcript",
      );
    });
  });

  it("disables dictation with a Settings tooltip when no STT provider is available", async () => {
    const user = userEvent.setup();
    renderComposer({
      dictationAvailable: false,
      dictationUnavailableReason:
        "Choose a speech-to-text provider in Settings to use dictation.",
      onTranscribeDictation: vi.fn(),
    });

    const mic = screen.getByRole("button", { name: "Start dictation" });
    expect(mic).toBeDisabled();

    const tooltipTrigger = mic.closest(".composer__input-tooltip-trigger");
    expect(tooltipTrigger).not.toBeNull();
    await user.hover(tooltipTrigger!);

    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Choose a speech-to-text provider in Settings to use dictation.",
    );
  });

  it("shows microphone permission errors without changing input or attachments", async () => {
    const user = userEvent.setup();
    createWavRecorderMock.mockRejectedValueOnce(
      new DOMException("Permission denied", "NotAllowedError"),
    );
    const { onSubmit } = renderComposer();
    const image = new File(["binary"], "diagram.png", { type: "image/png" });

    await user.upload(document.querySelector('input[name="image-upload"]')!, image);
    await user.click(screen.getByRole("button", { name: "Start dictation" }));

    expect(await screen.findByText("Microphone permission was denied.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("");
    expect(screen.getByText("diagram.png")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("shows transcription errors without changing input or attachments", async () => {
    const user = userEvent.setup();
    const onTranscribeDictation = vi.fn().mockRejectedValue(new Error("STT provider failed"));
    renderComposer({ onTranscribeDictation });
    const image = new File(["binary"], "diagram.png", { type: "image/png" });

    await user.upload(document.querySelector('input[name="image-upload"]')!, image);
    await user.click(screen.getByRole("button", { name: "Start dictation" }));
    await user.click(await screen.findByRole("button", { name: "Stop dictation recording" }));

    expect(await screen.findByText("STT provider failed")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("");
    expect(screen.getByText("diagram.png")).toBeInTheDocument();
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

  it("marks disabled skill suggestions", async () => {
    const user = userEvent.setup();
    vi.mocked(searchSkillMentions).mockResolvedValue({
      items: [
        {
          name: "writer",
          description: "Write prose",
          path: ".agents/skills/writer/SKILL.md",
          enabled: false,
        },
      ],
    });
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "$w");

    expect(await screen.findByText("disabled skill")).toBeInTheDocument();
  });

  it("shows mixed file and agent suggestions and inserts visible agent tags", async () => {
    const user = userEvent.setup();
    vi.mocked(searchAgentMentions).mockResolvedValue({
      items: [
        {
          name: "code-reviewer",
          description: "Review code changes",
          path: ".agents/agents/code-reviewer.md",
          enabled: false,
        },
      ],
    });
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [{ path: "code-reviewer-notes.md", kind: "file" }],
      scan_status: "ready",
      is_stale: false,
      file_count: 1,
      error: null,
    });
    renderComposer();

    const textbox = screen.getByRole("textbox", { name: "Message" });
    await user.type(textbox, "@code");

    expect(
      await screen.findByRole("listbox", {
        name: "Workspace file and agent suggestions",
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText("@code-reviewer (agent)")).toBeInTheDocument();
    expect(screen.getByText("disabled agent")).toBeInTheDocument();
    expect(screen.getByText("@code-reviewer-notes.md")).toBeInTheDocument();

    await user.keyboard("{Enter}");
    expect(textbox).toHaveValue("@code-reviewer (agent) ");
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
    const image = new File(["binary"], "diagram.heif");

    fireEvent.change(document.querySelector('input[name="image-upload"]')!, {
      target: { files: [image] },
    });
    expect(await screen.findByText("diagram.heif")).toBeInTheDocument();

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

  it("keeps idle submit behavior unchanged", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "normal follow up{enter}");

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
      text: "normal follow up",
      images: [],
    }));
    expect(screen.queryByRole("menu", { name: "Choose follow-up delivery" })).not.toBeInTheDocument();
  });

  it("opens follow-up timing choices when submitting during processing", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
    });

    await user.type(screen.getByRole("textbox", { name: "Message" }), "while busy{enter}");

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("menu", { name: "Choose follow-up delivery" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /After next safe checkpoint/ })).toHaveClass(
      "composer__completion-item--active",
    );
    expect(screen.getByRole("menuitem", { name: /After assistant finishes/ })).not.toHaveClass(
      "composer__completion-item--active",
    );
  });

  it("submits the default follow-up choice with Enter while the textbox keeps focus", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
    });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    await user.type(textbox, "default checkpoint{enter}");
    fireEvent.keyDown(textbox, { key: "Enter" });

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
      text: "default checkpoint",
      images: [],
      followUpDelivery: "checkpoint",
    }));
  });

  it("navigates follow-up timing choices with arrow keys", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
    });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    await user.type(textbox, "send later{enter}");
    fireEvent.keyDown(textbox, { key: "ArrowDown" });
    expect(screen.getByRole("menuitem", { name: /After assistant finishes/ })).toHaveClass(
      "composer__completion-item--active",
    );
    fireEvent.keyDown(textbox, { key: "Enter" });

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
      text: "send later",
      images: [],
      followUpDelivery: "after_finish",
    }));
  });

  it("wraps follow-up timing navigation upward and closes with Escape", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
    });
    const textbox = screen.getByRole("textbox", { name: "Message" });

    await user.type(textbox, "wrapped later{enter}");
    fireEvent.keyDown(textbox, { key: "ArrowUp" });
    expect(screen.getByRole("menuitem", { name: /After assistant finishes/ })).toHaveClass(
      "composer__completion-item--active",
    );
    fireEvent.keyDown(textbox, { key: "Escape" });

    expect(screen.queryByRole("menu", { name: "Choose follow-up delivery" })).not.toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("offers a clickable follow-up submit while interrupt is available", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
      canInterrupt: true,
      onInterrupt: vi.fn(),
    });

    expect(screen.getByRole("button", { name: "Interrupt assistant turn" })).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "while busy");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("menu", { name: "Choose follow-up delivery" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /After next safe checkpoint/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /After assistant finishes/ })).toBeInTheDocument();
  });

  it("sends checkpoint follow-ups to the backend queue immediately", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
    });

    await user.type(screen.getByRole("textbox", { name: "Message" }), "send at checkpoint{enter}");
    await user.click(screen.getByRole("menuitem", { name: /After next safe checkpoint/ }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
      text: "send at checkpoint",
      images: [],
      followUpDelivery: "checkpoint",
    }));
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("");
  });

  it("closes stale follow-up timing choices when the session becomes unsafe", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderWithProviders(
      <Composer
        inputEnabled={false}
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        isProcessing
        canQueueFollowUp
        onSubmit={onSubmit}
      />,
    );

    await user.type(screen.getByRole("textbox", { name: "Message" }), "while busy{enter}");
    expect(screen.getByRole("menu", { name: "Choose follow-up delivery" })).toBeInTheDocument();

    rerender(
      <Composer
        inputEnabled={false}
        sessionEnded
        liveSessionId={null}
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        isProcessing={false}
        canQueueFollowUp={false}
        onSubmit={onSubmit}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByRole("menu", { name: "Choose follow-up delivery" })).not.toBeInTheDocument();
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("blocks bang-prefixed checkpoint follow-ups while processing", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
    });

    await user.type(screen.getByRole("textbox", { name: "Message" }), "!pwd{enter}");
    await user.click(screen.getByRole("menuitem", { name: /After next safe checkpoint/ }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText("Shell commands cannot be sent as follow-ups while the assistant is processing."),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("!pwd");
  });

  it("activates follow-up timing choices from the keyboard", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
    });

    await user.type(screen.getByRole("textbox", { name: "Message" }), "keyboard checkpoint{enter}");
    screen.getByRole("menuitem", { name: /After next safe checkpoint/ }).focus();
    await user.keyboard("{Enter}");

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
      text: "keyboard checkpoint",
      images: [],
      followUpDelivery: "checkpoint",
    }));

    await user.type(screen.getByRole("textbox", { name: "Message" }), "keyboard later{enter}");
    screen.getByRole("menuitem", { name: /After assistant finishes/ }).focus();
    await user.keyboard(" ");

    await waitFor(() => expect(onSubmit).toHaveBeenLastCalledWith({
      text: "keyboard later",
      images: [],
      followUpDelivery: "after_finish",
    }));
  });

  it("queues after-finish follow-ups through submit", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
    });

    await user.type(screen.getByRole("textbox", { name: "Message" }), "queued for later{enter}");
    await user.click(screen.getByRole("menuitem", { name: /After assistant finishes/ }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
      text: "queued for later",
      images: [],
      followUpDelivery: "after_finish",
    }));
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("");
  });

  it("blocks bang-prefixed queued manual follow-ups while processing", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderComposer({
      inputEnabled: false,
      isProcessing: true,
      canQueueFollowUp: true,
    });

    await user.type(screen.getByRole("textbox", { name: "Message" }), "!pwd{enter}");
    await user.click(screen.getByRole("menuitem", { name: /After assistant finishes/ }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Queued follow-up")).not.toBeInTheDocument();
    expect(
      screen.getByText("Shell commands cannot be sent as follow-ups while the assistant is processing."),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("!pwd");
  });

  it("shows, edits, cancels, and manually sends a backend queued follow-up", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const onCancelQueuedFollowUp = vi.fn().mockResolvedValue(undefined);
    const onSendQueuedFollowUp = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <Composer
        inputEnabled
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        isProcessing={false}
        canQueueFollowUp
        queuedFollowUp={{
          id: "follow-1",
          delivery: "after_finish",
          text: "queued for later",
          file_paths: [],
          image_attachments: [],
          image_count: 0,
          created_at: "2026-06-29T00:00:00Z",
          failed: false,
          error: null,
        }}
        onSubmit={onSubmit}
        onCancelQueuedFollowUp={onCancelQueuedFollowUp}
        onSendQueuedFollowUp={onSendQueuedFollowUp}
      />,
    );

    expect(screen.getByLabelText("Queued follow-up")).toHaveTextContent("queued for later");
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => expect(onCancelQueuedFollowUp).toHaveBeenCalledWith("follow-1"));
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("queued for later");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancelQueuedFollowUp).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole("button", { name: "Send now" }));
    expect(onSendQueuedFollowUp).toHaveBeenCalledWith("follow-1");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables manual send-now for after-finish queued follow-ups while processing", async () => {
    const user = userEvent.setup();
    const onSendQueuedFollowUp = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <Composer
        inputEnabled={false}
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        isProcessing
        canQueueFollowUp
        queuedFollowUp={{
          id: "follow-1",
          delivery: "after_finish",
          text: "queued for later",
          file_paths: [],
          image_attachments: [],
          image_count: 0,
          created_at: "2026-06-29T00:00:00Z",
          failed: false,
          error: null,
        }}
        onSubmit={vi.fn()}
        onSendQueuedFollowUp={onSendQueuedFollowUp}
      />,
    );

    const sendNow = screen.getByRole("button", { name: "Send now" });
    expect(sendNow).toBeDisabled();
    await user.click(sendNow);
    expect(onSendQueuedFollowUp).not.toHaveBeenCalled();
  });

  it("renders backend queued follow-up failures", () => {
    renderWithProviders(
      <Composer
        inputEnabled={false}
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        isProcessing
        canQueueFollowUp
        queuedFollowUp={{
          id: "follow-1",
          delivery: "after_finish",
          text: "retry later",
          file_paths: [],
          image_attachments: [],
          image_count: 1,
          created_at: "2026-06-29T00:00:00Z",
          failed: true,
          error: "Auto-send failed",
        }}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Queued follow-up")).toHaveTextContent("retry later");
    expect(screen.getByText("Auto-send failed")).toBeInTheDocument();
    expect(screen.getByLabelText("Queued follow-up")).toHaveTextContent("1 image");
  });

  it("renders checkpoint queued follow-ups without manual send-now", () => {
    renderWithProviders(
      <Composer
        inputEnabled={false}
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        isProcessing
        canQueueFollowUp
        queuedFollowUp={{
          id: "follow-1",
          delivery: "checkpoint",
          text: "steer current turn",
          file_paths: [],
          image_attachments: [],
          image_count: 0,
          created_at: "2026-06-29T00:00:00Z",
          failed: false,
          error: null,
        }}
        onSubmit={vi.fn()}
        onSendQueuedFollowUp={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Queued follow-up")).toHaveTextContent(
      "after next checkpoint",
    );
    expect(screen.getByRole("button", { name: "Send now" })).toBeDisabled();
  });

  it("renders multiple queued follow-ups and still accepts another draft", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <Composer
        inputEnabled={false}
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        isProcessing
        canQueueFollowUp
        queuedFollowUps={[
          {
            id: "follow-1",
            delivery: "checkpoint",
            text: "first queued",
            file_paths: [],
            image_attachments: [],
            image_count: 0,
            created_at: "2026-06-29T00:00:00Z",
            failed: false,
            error: null,
          },
          {
            id: "follow-2",
            delivery: "after_finish",
            text: "second queued",
            file_paths: [],
            image_attachments: [],
            image_count: 0,
            created_at: "2026-06-29T00:00:01Z",
            failed: false,
            error: null,
          },
        ]}
        onSubmit={onSubmit}
        onSendQueuedFollowUp={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Queued follow-ups")).toHaveTextContent("first queued");
    expect(screen.getByLabelText("Queued follow-ups")).toHaveTextContent("second queued");

    await user.type(screen.getByRole("textbox", { name: "Message" }), "third queued{enter}");
    await user.click(screen.getByRole("menuitem", { name: /After assistant finishes/ }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
      text: "third queued",
      images: [],
      followUpDelivery: "after_finish",
    }));
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

  it("shows built-in and project badges on slash command suggestions", async () => {
    const user = userEvent.setup();
    vi.mocked(searchSlashCommands).mockResolvedValue([
      {
        name: "/new",
        description: "Start a fresh session",
        kind: "local_command",
      },
      {
        name: "/review",
        description: "Review recent changes",
        kind: "command",
      },
    ]);
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "/");

    await screen.findByRole("listbox", {
      name: "Slash command suggestions",
    });
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(2));
    const builtInBadge = await screen.findByText("built-in");
    const projectBadge = await screen.findByText("project");
    expect(builtInBadge.closest(".composer__completion-kind--built-in")).not.toBeNull();
    expect(projectBadge.closest(".composer__completion-kind--project")).not.toBeNull();
  });

  it("loads slash commands beyond the old eight-item cap into the anchored popup", async () => {
    const user = userEvent.setup();
    const commands = Array.from({ length: 12 }, (_, index) => ({
      name: `/command-${index + 1}`,
      description: `Command ${index + 1}`,
      kind: "local_command" as const,
    }));
    vi.mocked(searchSlashCommands).mockResolvedValue(commands);
    renderComposer();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "/");

    const listbox = await screen.findByRole("listbox", {
      name: "Slash command suggestions",
    });
    await waitFor(() =>
      expect(searchSlashCommands).toHaveBeenCalledWith("", 200),
    );
    expect(listbox.closest(".composer")).not.toBeNull();
    await waitFor(() =>
      expect(screen.getAllByRole("option")).toHaveLength(commands.length),
    );
    expect(screen.getByText("/command-12", { exact: false })).toBeInTheDocument();
  });
});
