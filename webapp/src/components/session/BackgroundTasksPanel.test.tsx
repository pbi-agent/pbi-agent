import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BackgroundTasksPanel, formatElapsed } from "./BackgroundTasksPanel";
import type { BackgroundTask } from "../../types";

const task = (overrides: Partial<BackgroundTask> = {}): BackgroundTask => ({
  task_id: "bg-1",
  command: "npm run build",
  working_directory: "/w",
  status: "running",
  started_at: Date.now() / 1000,
  elapsed_seconds: 3,
  ...overrides,
});

describe("BackgroundTasksPanel", () => {
  it("shows an empty state without tasks", () => {
    render(<BackgroundTasksPanel sessionId="s" tasks={[]} />);
    expect(screen.getByText("No background tasks")).toBeInTheDocument();
  });

  it("lists tasks, kills on request, and closes", () => {
    const onKill = vi.fn();
    const onClose = vi.fn();
    render(
      <BackgroundTasksPanel
        sessionId="s"
        tasks={[task(), task({ task_id: "bg-2", command: "make", status: "failed", exit_code: 2 })]}
        onKill={onKill}
        onClose={onClose}
      />,
    );
    expect(screen.getByText("1 running · 1 finished")).toBeInTheDocument();
    expect(screen.getByText("npm run build", { selector: "code" })).toBeInTheDocument();
    expect(screen.getByText(/Failed · exit 2/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Kill/ }));
    expect(onKill).toHaveBeenCalledWith("bg-1");
    fireEvent.click(screen.getByRole("button", { name: "Close background tasks panel" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("formats elapsed time", () => {
    expect(formatElapsed(65)).toBe("1m 5s");
    expect(formatElapsed(4.7)).toBe("4s");
  });
});
