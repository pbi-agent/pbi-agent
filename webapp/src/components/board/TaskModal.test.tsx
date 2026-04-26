import { screen } from "@testing-library/react";
import { TaskModal, type EditableTask } from "./TaskModal";
import { renderWithProviders } from "../../test/render";
import type { BoardStage, ModelProfileView } from "../../types";

const task: EditableTask = {
  title: "Draft implementation plan",
  prompt: "Write a careful implementation plan.",
  stage: "backlog",
  projectDir: "/workspace/project",
  sessionId: "",
  profileId: "",
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
});