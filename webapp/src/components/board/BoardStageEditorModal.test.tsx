import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
import { BoardStageEditorModal } from "./BoardStageEditorModal";
import { renderWithProviders } from "../../test/render";
import type { BoardStage, CommandView, ModelProfileView } from "../../types";

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

const commands: CommandView[] = [
  {
    id: "plan",
    name: "Plan",
    slash_alias: "/plan",
    description: "Plan before coding",
    instructions: "Plan first",
    path: ".agents/commands/plan.md",
  },
];

describe("BoardStageEditorModal", () => {
  it("inserts a new stage before Done when requested and submits edited values", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);

    renderWithProviders(
      <BoardStageEditorModal
        stages={stages}
        profiles={profiles}
        commands={commands}
        startWithNewStage
        isSaving={false}
        onSave={onSave}
        onClose={() => {}}
      />,
    );

    const stageNameInput = screen.getAllByRole("textbox").find(
      (textbox) => !textbox.hasAttribute("disabled"),
    );
    if (!stageNameInput) {
      throw new Error("Expected an editable stage name input.");
    }
    await user.type(stageNameInput, "Implement");

    const selects = screen.getAllByRole("combobox").filter(
      (combobox) => !combobox.hasAttribute("disabled"),
    );
    const [profileSelect, commandSelect] = selects;
    if (!profileSelect || !commandSelect) {
      throw new Error("Expected editable profile and command selects.");
    }
    await user.selectOptions(profileSelect, "analysis");
    await user.selectOptions(commandSelect, "plan");
    const editableToggle = screen.getAllByRole("checkbox").find((checkbox) => !checkbox.hasAttribute("disabled"));
    if (!editableToggle) {
      throw new Error("Expected an editable auto-start toggle.");
    }
    await user.click(editableToggle);
    await user.click(screen.getByRole("button", { name: "Save Board" }));

    expect(onSave).toHaveBeenCalledWith([
      {
        id: "backlog",
        name: "Backlog",
        profile_id: "",
        command_id: "",
        auto_start: false,
      },
      {
        id: "",
        name: "Implement",
        profile_id: "analysis",
        command_id: "plan",
        auto_start: true,
      },
      {
        id: "done",
        name: "Done",
        profile_id: "",
        command_id: "",
        auto_start: false,
      },
    ]);
  });
});
