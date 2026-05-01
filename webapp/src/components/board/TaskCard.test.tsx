import userEvent from "@testing-library/user-event";
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
  it("renders the start shortcut for idle runnable tasks", () => {
    renderWithProviders(
      <TaskCard
        task={makeTask()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRun={vi.fn()}
        canRun
      />,
    );

    expect(screen.getByRole("button", { name: "Start" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Stop/ })).not.toBeInTheDocument();
  });

  it("replaces start with stop when the task has an active live session", async () => {
    const user = userEvent.setup();
    const onInterrupt = vi.fn();

    renderWithProviders(
      <TaskCard
        task={makeTask({ run_status: "running" })}
        activeLiveSessionId="live-1"
        onInterrupt={onInterrupt}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRun={vi.fn()}
        canRun
      />,
    );

    expect(screen.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();

    const stopButton = screen.getByRole("button", { name: "Stop Draft spec" });
    await user.click(stopButton);

    expect(onInterrupt).toHaveBeenCalledTimes(1);
  });

  it("disables stop while interrupting the active live session", () => {
    renderWithProviders(
      <TaskCard
        task={makeTask({ run_status: "running" })}
        activeLiveSessionId="live-1"
        isInterrupting
        onInterrupt={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRun={vi.fn()}
        canRun
      />,
    );

    expect(screen.getByRole("button", { name: "Stop Draft spec" })).toBeDisabled();
  });

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

  it("does not render technical project or session metadata in the card content", () => {
    renderWithProviders(
      <TaskCard
        task={makeTask({ project_dir: "technical/project", session_id: "technical-session-id" })}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRun={vi.fn()}
        canRun
      />,
    );

    expect(screen.queryByText("technical/project")).not.toBeInTheDocument();
    expect(screen.queryByText("technical-session-id")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Session" })).toHaveAttribute(
      "href",
      "/sessions/technical-session-id",
    );
  });

  it("does not render a no session fallback for tasks without sessions", () => {
    renderWithProviders(
      <TaskCard
        task={makeTask({ session_id: null })}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRun={vi.fn()}
        canRun
      />,
    );

    expect(screen.queryByText("no session")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Session" })).not.toBeInTheDocument();
  });
});
