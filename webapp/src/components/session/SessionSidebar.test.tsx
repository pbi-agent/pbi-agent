import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";
import { SessionSidebar } from "./SessionSidebar";
import type { SessionRecord } from "../../types";

function makeSession(overrides: Partial<SessionRecord> = {}): SessionRecord {
  return {
    session_id: "session-1",
    directory: "/workspace",
    provider: "openai",
    provider_id: "openai-main",
    model: "gpt-5.4",
    profile_id: "analysis",
    previous_id: null,
    title: "Planning session",
    total_tokens: 0,
    input_tokens: 0,
    output_tokens: 0,
    cost_usd: 0,
    created_at: "2026-04-16T10:00:00Z",
    updated_at: "2026-04-16T10:00:00Z",
    ...overrides,
  };
}

function renderSidebar(overrides: Partial<Parameters<typeof SessionSidebar>[0]> = {}) {
  const props = {
    sessions: [makeSession()],
    isLoading: false,
    activeSessionId: null,
    onNewSession: vi.fn(),
    onResumeSession: vi.fn(),
    onUpdateSession: vi.fn().mockResolvedValue(undefined),
    onDeleteSession: vi.fn(),
    onToggle: vi.fn(),
    isOpen: true,
    ...overrides,
  };
  render(<SessionSidebar {...props} />);
  return props;
}

describe("SessionSidebar", () => {
  it("opens the edit action and saves a changed title", async () => {
    const user = userEvent.setup();
    const props = renderSidebar();

    await user.click(screen.getByRole("button", { name: "Open actions for Planning session" }));
    await user.click(await screen.findByRole("menuitem", { name: /edit title/i }));

    const input = screen.getByLabelText("Session title");
    expect(input).toHaveValue("Planning session");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    await user.clear(input);
    await user.type(input, "Updated roadmap");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(props.onUpdateSession).toHaveBeenCalledWith(
        props.sessions[0],
        "Updated roadmap",
      );
    });
  });

  it("cancels inline title editing without saving", async () => {
    const user = userEvent.setup();
    const props = renderSidebar();

    await user.click(screen.getByRole("button", { name: "Open actions for Planning session" }));
    await user.click(await screen.findByRole("menuitem", { name: /edit title/i }));
    await user.clear(screen.getByLabelText("Session title"));
    await user.type(screen.getByLabelText("Session title"), "Discard me");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(props.onUpdateSession).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Session title")).toBeNull();
    expect(screen.getByText("Planning session")).toBeInTheDocument();
  });

  it("keeps save disabled for blank titles", async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByRole("button", { name: "Open actions for Planning session" }));
    await user.click(await screen.findByRole("menuitem", { name: /edit title/i }));
    await user.clear(screen.getByLabelText("Session title"));
    await user.type(screen.getByLabelText("Session title"), "   ");

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });
});
