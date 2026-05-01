import { screen } from "@testing-library/react";
import { TaskCard } from "./TaskCard";
import { renderWithProviders } from "../../test/render";
import type { TaskRecord } from "../../types";

vi.mock("@dnd-kit/core", () => ({
  useDraggable: () => ({
    attributes: {},
    listeners: {},
    setNodeRef: vi.fn(),
    isDragging: false,
  }),
}));

function makeTask(overrides: Partial<TaskRecord> = {}): TaskRecord {
  return {
    task_id: "task-1",
    directory: "/workspace",
    title: "Draft spec",
    prompt: "Write the spec",
    stage: "backlog",
    position: 0,
    project_dir: ".",
    session_id: "session 1/with slash",
    profile_id: null,
    run_status: "idle",
    last_result_summary: "",
    created_at: "2026-04-16T10:00:00Z",
    updated_at: "2026-04-16T10:00:00Z",
    last_run_started_at: null,
    last_run_finished_at: null,
    image_attachments: [],
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

describe("TaskCard", () => {
  it("links to the task session in the same tab", () => {
    renderWithProviders(
      <TaskCard
        task={makeTask()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRun={vi.fn()}
        canRun
      />,
    );

    const link = screen.getByRole("link", { name: "Session" });
    expect(link).toHaveAttribute("href", "/sessions/session%201%2Fwith%20slash");
    expect(link).not.toHaveAttribute("target");
    expect(link).not.toHaveAttribute("rel");
  });
});