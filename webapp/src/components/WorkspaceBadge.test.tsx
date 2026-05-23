import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { renderWithProviders } from "../test/render";
import type { BootstrapPayload, WorkspaceListPayload } from "../types";
import { WorkspaceBadge } from "./WorkspaceBadge";

const mocks = vi.hoisted(() => ({
  fetchBootstrap: vi.fn(),
  fetchRecentWorkspaces: vi.fn(),
  switchWorkspace: vi.fn(),
  pickWorkspace: vi.fn(),
}));

vi.mock("../api", () => mocks);

function makeBootstrap(root: string): BootstrapPayload {
  return {
    workspace_root: root,
    workspace_key: root,
    workspace_display_path: root,
    is_sandbox: false,
    provider: "openai",
    provider_id: null,
    profile_id: null,
    model: "gpt-5.4",
    reasoning_effort: "medium",
    supports_image_inputs: true,
    sessions: [],
    tasks: [],
    live_sessions: [],
    board_stages: [],
  };
}

describe("WorkspaceBadge", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("opens the workspace switcher and switches to a recent workspace", async () => {
    const user = userEvent.setup();
    const initial = makeBootstrap("/workspaces/alpha");
    const switched = makeBootstrap("/workspaces/beta");
    const recent: WorkspaceListPayload = {
      picker_available: true,
      workspaces: [
        {
          directory_key: "/workspaces/alpha",
          root_path: "/workspaces/alpha",
          display_path: "/workspaces/alpha",
          is_sandbox: false,
          last_opened_at: "2026-05-23T10:00:00Z",
          is_current: true,
        },
        {
          directory_key: "/workspaces/beta",
          root_path: "/workspaces/beta",
          display_path: "/workspaces/beta",
          is_sandbox: false,
          last_opened_at: "2026-05-23T11:00:00Z",
          is_current: false,
        },
      ],
    };
    mocks.fetchBootstrap
      .mockResolvedValueOnce(initial)
      .mockResolvedValue(switched);
    mocks.fetchRecentWorkspaces.mockResolvedValue(recent);
    mocks.switchWorkspace.mockResolvedValue({ bootstrap: switched });

    const { queryClient } = renderWithProviders(<WorkspaceBadge />);

    await screen.findByRole("button", { name: "Switch workspace" });
    expect(screen.getByText("workspaces/alpha")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Switch workspace" }));
    expect(await screen.findByRole("dialog", { name: "Switch workspace" }))
      .toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /beta/ }));

    await waitFor(() => {
      expect(mocks.switchWorkspace.mock.calls[0]?.[0]).toBe("/workspaces/beta");
    });
    await waitFor(() => {
      expect(queryClient.getQueryData(["bootstrap"])).toEqual(switched);
    });
  });

  it("shows a clear unavailable state when folder picking is unsupported", async () => {
    const user = userEvent.setup();
    mocks.fetchBootstrap.mockResolvedValue(makeBootstrap("/workspaces/alpha"));
    mocks.fetchRecentWorkspaces.mockResolvedValue({
      picker_available: false,
      workspaces: [],
    });

    renderWithProviders(<WorkspaceBadge />);

    await user.click(
      await screen.findByRole("button", { name: "Switch workspace" }),
    );

    expect(await screen.findByText("No recent workspaces yet.")).toBeInTheDocument();
    const warning = screen.getByRole("alert");
    expect(warning).toHaveClass("workspace-switcher-dialog__warning");
    expect(warning).toHaveTextContent(
      "Native folder picking is not available in this environment.",
    );
    expect(screen.getByRole("button", { name: /Choose folder/ })).toBeEnabled();
  });
});