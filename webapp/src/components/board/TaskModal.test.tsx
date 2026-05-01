import { fireEvent, screen } from "@testing-library/react";
import { TaskModal, type EditableTask } from "./TaskModal";
import { renderWithProviders } from "../../test/render";
import type { BoardStage, ModelProfileView } from "../../types";

beforeEach(() => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:task-image"),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const task: EditableTask = {
  title: "Draft implementation plan",
  prompt: "Write a careful implementation plan.",
  stage: "backlog",
  projectDir: "/workspace/project",
  sessionId: "",
  profileId: "",
  imageAttachments: [],
  imageFiles: [],
  imageError: null,
};

const stages: BoardStage[] = [
  {
    id: "backlog",
    name: "Backlog",
    position: 0,
    profile_id: null,
    command_id: null,
    auto_start: false,
  },
  {
    id: "done",
    name: "Done",
    position: 1,
    profile_id: null,
    command_id: null,
    auto_start: false,
  },
];

function clipboardFileItem(file: File): DataTransferItem {
  return {
    kind: "file",
    type: file.type,
    getAsFile: () => file,
  } as DataTransferItem;
}

function clipboardTextItem(text: string): DataTransferItem {
  return {
    kind: "string",
    type: "text/plain",
    getAsFile: () => null,
    getAsString: (callback: (data: string) => void) => callback(text),
  } as DataTransferItem;
}

function pasteInto(element: HTMLElement, items: DataTransferItem[]): Event {
  const event = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clipboardData", {
    value: { items },
  });
  element.dispatchEvent(event);
  return event;
}

const profiles: ModelProfileView[] = [
  {
    id: "analysis",
    name: "Analysis",
    provider_id: "openai-main",
    provider: { id: "openai-main", name: "OpenAI Main", kind: "openai" },
    model: "gpt-5.4",
    sub_agent_model: null,
    reasoning_effort: "high",
    max_tokens: null,
    service_tier: null,
    web_search: false,
    max_tool_workers: null,
    max_retries: null,
    compact_threshold: null,
    compact_tail_turns: 2,
    compact_preserve_recent_tokens: 8000,
    compact_tool_output_max_chars: 2000,
    is_active_default: true,
    resolved_runtime: {
      provider: "OpenAI",
      provider_id: "openai-main",
      profile_id: "analysis",
      model: "gpt-5.4",
      sub_agent_model: null,
      reasoning_effort: "high",
      max_tokens: 0,
      service_tier: null,
      web_search: false,
      max_tool_workers: 1,
      max_retries: 1,
      compact_threshold: 1,
      compact_tail_turns: 2,
      compact_preserve_recent_tokens: 8000,
      compact_tool_output_max_chars: 2000,
      responses_url: "https://api.openai.com/v1/responses",
      generic_api_url: "https://api.openai.com/v1/chat/completions",
      supports_image_inputs: true,
    },
  },
];

describe("TaskModal", () => {
  it("renders the new task form in the DESIGN-aligned dialog shell", () => {
    renderWithProviders(
      <TaskModal
        task={task}
        boardStages={stages}
        profiles={profiles}
        isSaving={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const dialog = screen.getByRole("dialog", { name: "New Task" });
    expect(dialog).toHaveClass("task-form-dialog");
    expect(screen.getByRole("heading", { name: "New Task" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Draft implementation plan")).toHaveClass("task-form__input");
    expect(screen.getByDisplayValue("Write a careful implementation plan.")).toHaveClass("task-form__textarea");
    expect(screen.getByRole("combobox", { name: "Stage" })).toHaveClass("task-form__select");
    expect(screen.getByRole("combobox", { name: "Profile Override" })).toHaveClass("task-form__select");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("reports selected image files through onChange", () => {
    const onChange = vi.fn();
    renderWithProviders(
      <TaskModal
        task={task}
        boardStages={stages}
        profiles={profiles}
        isSaving={false}
        onChange={onChange}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const input = document.querySelector<HTMLInputElement>('input[name="task-image-upload"]');
    expect(input).not.toBeNull();
    const file = new File(["binary"], "mockup.png", { type: "image/png" });
    fireEvent.change(input!, { target: { files: [file] } });

    expect(onChange).toHaveBeenCalledOnce();
    const update = onChange.mock.calls[0]?.[0] as Partial<EditableTask>;
    expect(update.imageError).toBeNull();
    expect(update.imageFiles).toHaveLength(1);
    expect(update.imageFiles?.[0]?.file).toBe(file);
    expect(update.imageFiles?.[0]?.previewUrl).toBe("blob:task-image");
  });

  it("attaches pasted prompt image files through onChange", () => {
    const onChange = vi.fn();
    renderWithProviders(
      <TaskModal
        task={task}
        boardStages={stages}
        profiles={profiles}
        isSaving={false}
        onChange={onChange}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const prompt = screen.getByLabelText("Prompt");
    const file = new File(["binary"], "screenshot.png", { type: "image/png" });
    const pasteEvent = pasteInto(prompt, [clipboardFileItem(file)]);

    expect(pasteEvent.defaultPrevented).toBe(true);
    expect(onChange).toHaveBeenCalledOnce();
    const update = onChange.mock.calls[0]?.[0] as Partial<EditableTask>;
    expect(update.imageError).toBeNull();
    expect(update.imageFiles).toHaveLength(1);
    expect(update.imageFiles?.[0]?.file).toBe(file);
    expect(update.imageFiles?.[0]?.previewUrl).toBe("blob:task-image");
  });

  it("leaves normal prompt text paste unchanged", () => {
    const onChange = vi.fn();
    renderWithProviders(
      <TaskModal
        task={task}
        boardStages={stages}
        profiles={profiles}
        isSaving={false}
        onChange={onChange}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const prompt = screen.getByLabelText("Prompt");
    const pasteEvent = pasteInto(prompt, [clipboardTextItem("plain prompt text")]);

    expect(pasteEvent.defaultPrevented).toBe(false);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("reports unsupported pasted image types", () => {
    const onChange = vi.fn();
    renderWithProviders(
      <TaskModal
        task={task}
        boardStages={stages}
        profiles={profiles}
        isSaving={false}
        onChange={onChange}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const prompt = screen.getByLabelText("Prompt");
    const file = new File(["binary"], "animation.gif", { type: "image/gif" });
    const pasteEvent = pasteInto(prompt, [clipboardFileItem(file)]);

    expect(pasteEvent.defaultPrevented).toBe(true);
    expect(onChange).toHaveBeenCalledWith({
      imageError: "Only PNG, JPEG, and WEBP images are supported.",
    });
  });
});
