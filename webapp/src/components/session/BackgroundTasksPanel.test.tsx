import { fireEvent, render as rtlRender, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { getBackgroundTaskOutput } from "../../api";

vi.mock("../../api", () => ({ getBackgroundTaskOutput: vi.fn() }));
import { BackgroundTasksPanel, formatElapsed } from "./BackgroundTasksPanel";
import type { BackgroundTask } from "../../types";

const render = (ui: ReactElement) =>
  rtlRender(
    <MemoryRouter initialEntries={["/sessions/s"]}>
      <Routes>
        <Route path="/sessions/:sessionId" element={ui} />
        <Route path="/sessions/:sessionId/sub-agents/:subAgentId" element={<p>sub-agent page</p>} />
      </Routes>
    </MemoryRouter>,
  );

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

  it("labels background sub-agents by intent and navigates to their session", () => {
    render(
      <BackgroundTasksPanel
        sessionId="s"
        tasks={[task({ kind: "sub_agent", intent: "Audit auth", command: "long task", sub_agent_id: "subagent-1" })]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open Audit auth agent session" }));
    expect(screen.getByText("sub-agent page")).toBeInTheDocument();
  });

  it("shows stored output for sub-agents that failed before getting an agent id", async () => {
    vi.mocked(getBackgroundTaskOutput).mockResolvedValue({
      task_id: "bg-1", status: "failed", stdout: "", stderr: "startup boom",
    } as never);
    render(
      <BackgroundTasksPanel
        sessionId="s"
        tasks={[task({ kind: "sub_agent", status: "failed", intent: "Audit auth", sub_agent_id: null })]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Toggle output for Audit auth" }));
    expect(await screen.findByText("startup boom")).toBeInTheDocument();
  });

  it("formats elapsed time", () => {
    expect(formatElapsed(65)).toBe("1m 5s");
    expect(formatElapsed(4.7)).toBe("4s");
  });
});
