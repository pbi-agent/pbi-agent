import type { ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { BoardPage } from "./BoardPage";
import { renderWithProviders } from "../../test/render";
import {
  ApiError,
  fetchBoardStages,
  fetchConfigBootstrap,
  fetchTasks,
  updateBoardStages,
} from "../../api";
import type {
  BoardStage,
  ConfigBootstrapPayload,
  TaskRecord,
} from "../../types";

vi.mock("@dnd-kit/core", () => ({
  DndContext: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DragOverlay: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  closestCenter: vi.fn(),
}));

vi.mock("@dnd-kit/sortable", () => ({
  SortableContext: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  horizontalListSortingStrategy: {},
  arrayMove: <T,>(items: T[], from: number, to: number) => {
    const next = [...items];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    return next;
  },
}));

vi.mock("./StageColumn", () => ({
  StageColumn: ({
    stage,
    tasks,
    onRun,
  }: {
    stage: BoardStage;
    tasks: TaskRecord[];
    onRun: (taskId: string) => void;
  }) => (
    <section data-testid={`stage-${stage.id}`}>
      <h3>{stage.name}</h3>
      {tasks.map((task) => (
        <button key={task.task_id} type="button" onClick={() => onRun(task.task_id)}>
          Run {task.title}
        </button>
      ))}
    </section>
  ),
}));

vi.mock("./TaskCard", () => ({
  TaskCardContent: ({ task }: { task: TaskRecord }) => <div>{task.title}</div>,
}));

vi.mock("./TaskModal", () => ({
  TaskModal: () => <div>Task Modal</div>,
}));

vi.mock("./BoardStageEditorModal", () => ({
  BoardStageEditorModal: ({
    startWithNewStage,
    onSave,
  }: {
    startWithNewStage: boolean;
    onSave: (stages: Array<{
      id: string;
      name: string;
      profile_id: string;
      command_id: string;
      auto_start: boolean;
    }>) => Promise<void>;
  }) => (
    <div>
      <div>Board Editor {startWithNewStage ? "new" : "existing"}</div>
      <button
        type="button"
        onClick={() => {
          void onSave([
            {
              id: "backlog",
              name: "Backlog",
              profile_id: "",
              command_id: "",
              auto_start: false,
            },
            {
              id: "implement",
              name: "Implement",
              profile_id: "stale-profile",
              command_id: "stale-command",
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
        }}
      >
        Save Mock Board
      </button>
    </div>
  ),
}));

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    fetchTasks: vi.fn(),
    fetchBoardStages: vi.fn(),
    fetchConfigBootstrap: vi.fn(),
    createTask: vi.fn(),
    updateTask: vi.fn(),
    deleteTask: vi.fn(),
    runTask: vi.fn(),
    updateBoardStages: vi.fn(),
  };
});

function makeTask(overrides: Partial<TaskRecord> = {}): TaskRecord {
  return {
    task_id: "task-1",
    directory: "/workspace",
    title: "Draft spec",
    prompt: "Write the spec",
    stage: "backlog",
    position: 0,
    project_dir: ".",
    session_id: null,
    profile_id: null,
    run_status: "idle",
    last_result_summary: "",
    created_at: "2026-04-16T10:00:00Z",
    updated_at: "2026-04-16T10:00:00Z",
    last_run_started_at: null,
    last_run_finished_at: null,
    runtime_summary: {
      provider: null,
      provider_id: null,
      profile_id: null,
      model: null,
      reasoning_effort: null,
    },
    ...overrides,
  };
}

function makeConfigBootstrap(
  overrides: Partial<ConfigBootstrapPayload> = {},
): ConfigBootstrapPayload {
  return {
    config_revision: "rev-1",
    active_profile_id: "analysis",
    providers: [],
    model_profiles: [
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
    ],
    commands: [
      {
        id: "plan",
        name: "Plan",
        slash_alias: "/plan",
        description: "Plan first",
        instructions: "Plan carefully",
        path: ".agents/commands/plan.md",
      },
    ],
    options: {
      provider_kinds: ["openai"],
      reasoning_efforts: ["high"],
      openai_service_tiers: [],
      provider_metadata: {
        openai: {
          label: "OpenAI API",
          description: "Uses an OpenAI API key.",
          default_auth_mode: "api_key",
          auth_modes: ["api_key"],
          auth_mode_metadata: {
            api_key: {
              label: "API key",
              account_label: null,
              supported_methods: [],
            },
          },
          default_model: "gpt-5.4",
          default_sub_agent_model: null,
          default_responses_url: null,
          default_generic_api_url: null,
          supports_responses_url: true,
          supports_generic_api_url: false,
          supports_service_tier: true,
          supports_native_web_search: true,
          supports_image_inputs: true,
        },
      },
    },
    ...overrides,
  };
}

describe("BoardPage", () => {
  const backlogAndDoneStages: BoardStage[] = [
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

  beforeEach(() => {
    vi.mocked(fetchTasks).mockResolvedValue([]);
    vi.mocked(fetchBoardStages).mockResolvedValue(backlogAndDoneStages);
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(makeConfigBootstrap());
    vi.mocked(updateBoardStages).mockResolvedValue(backlogAndDoneStages);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the empty state when no tasks are returned", async () => {
    renderWithProviders(<BoardPage />);

    expect(await screen.findByText("No tasks yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add Task" })).toHaveLength(2);
  });

  it("prompts for runnable stage creation before running backlog tasks", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchTasks).mockResolvedValue([makeTask()]);

    renderWithProviders(<BoardPage />);

    await user.click(await screen.findByRole("button", { name: "Run Draft spec" }));

    expect(screen.getByText("Create Runnable Stage")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create Stage" }));

    expect(await screen.findByText("Board Editor new")).toBeInTheDocument();
  });

  it("orders done tasks by creation date descending", async () => {
    vi.mocked(fetchTasks).mockResolvedValue([
      makeTask({
        task_id: "done-old",
        title: "Old done task",
        stage: "done",
        position: 0,
        created_at: "2026-04-01T00:00:00Z",
      }),
      makeTask({
        task_id: "done-new",
        title: "New done task",
        stage: "done",
        position: 1,
        created_at: "2026-04-20T00:00:00Z",
      }),
    ]);

    renderWithProviders(<BoardPage />);

    const doneStage = await screen.findByTestId("stage-done");
    const doneTasks = screen.getAllByRole("button", { name: /Run .* done task/ });

    expect(doneStage).toContainElement(doneTasks[0]);
    expect(doneTasks.map((task) => task.textContent)).toEqual([
      "Run New done task",
      "Run Old done task",
    ]);
  });

  it("refreshes config and retries board-stage saves when references are stale", async () => {
    const user = userEvent.setup();

    vi.mocked(fetchConfigBootstrap)
      .mockResolvedValueOnce(makeConfigBootstrap())
      .mockResolvedValueOnce(makeConfigBootstrap({ model_profiles: [], commands: [] }));
    vi.mocked(updateBoardStages)
      .mockRejectedValueOnce(new ApiError("Unknown profile ID: stale-profile", 400))
      .mockResolvedValueOnce(backlogAndDoneStages);

    renderWithProviders(<BoardPage />);

    await user.click(await screen.findByRole("button", { name: "Edit Stages" }));
    await user.click(screen.getByRole("button", { name: "Save Mock Board" }));

    await waitFor(() => expect(updateBoardStages).toHaveBeenCalledTimes(2));
    expect(fetchConfigBootstrap).toHaveBeenCalledTimes(2);
    expect(vi.mocked(updateBoardStages).mock.calls[0]?.[0]).toEqual({
      board_stages: [
        {
          id: "backlog",
          name: "Backlog",
          profile_id: null,
          command_id: null,
          auto_start: false,
        },
        {
          id: "implement",
          name: "Implement",
          profile_id: "stale-profile",
          command_id: "stale-command",
          auto_start: true,
        },
        {
          id: "done",
          name: "Done",
          profile_id: null,
          command_id: null,
          auto_start: false,
        },
      ],
    });
    expect(vi.mocked(updateBoardStages).mock.calls[1]?.[0]).toEqual({
      board_stages: [
        {
          id: "backlog",
          name: "Backlog",
          profile_id: null,
          command_id: null,
          auto_start: false,
        },
        {
          id: "implement",
          name: "Implement",
          profile_id: null,
          command_id: null,
          auto_start: true,
        },
        {
          id: "done",
          name: "Done",
          profile_id: null,
          command_id: null,
          auto_start: false,
        },
      ],
    });
  });
});
