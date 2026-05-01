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

  it("keeps the image attachment count visible", () => {
    renderWithProviders(
      <TaskCard
        task={makeTask({
          image_attachments: [
            {
              upload_id: "image-1",
              name: "first.png",
              mime_type: "image/png",
              byte_count: 12,
              preview_url: "/api/live-sessions/uploads/image-1",
            },
            {
              upload_id: "image-2",
              name: "second.png",
              mime_type: "image/png",
              byte_count: 34,
              preview_url: "/api/live-sessions/uploads/image-2",
            },
          ],
        })}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRun={vi.fn()}
        canRun
      />,
    );

    expect(screen.getByText("2")).toBeInTheDocument();
  });
});
