import userEvent from "@testing-library/user-event";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TooltipProvider } from "../ui/tooltip";
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
    searchQuery: "",
    onSearchQueryChange: vi.fn(),
    ...overrides,
  };
  render(
    <MemoryRouter>
      <TooltipProvider>
        <SessionSidebar {...props} />
      </TooltipProvider>
    </MemoryRouter>,
  );
  return props;
}

describe("SessionSidebar", () => {
  it("renders the session list header with a New Session action", async () => {
    const user = userEvent.setup();
    const props = renderSidebar();

    expect(screen.getByRole("heading", { name: "Sessions" })).toBeInTheDocument();
    const newButton = screen.getByRole("button", { name: /new/i });
    await user.click(newButton);
    expect(props.onNewSession).toHaveBeenCalledTimes(1);
  });

  it("renders a session search box and forwards edits", () => {
    const props = renderSidebar();

    const search = screen.getByRole("searchbox", { name: "Search sessions" });
    fireEvent.change(search, { target: { value: "roadmap" } });

    expect(props.onSearchQueryChange).toHaveBeenCalledWith("roadmap");
  });

  it("clears the session search from the styled clear button", async () => {
    const user = userEvent.setup();
    const props = renderSidebar({ searchQuery: "roadmap" });

    const search = screen.getByRole("searchbox", { name: "Search sessions" });
    await user.click(screen.getByRole("button", { name: "Clear session search" }));

    expect(props.onSearchQueryChange).toHaveBeenCalledWith("");
    expect(search).toHaveFocus();
  });

  it("renders a searched empty state", () => {
    renderSidebar({ sessions: [], searchQuery: "missing" });

    expect(screen.getByText("No matching sessions")).toBeInTheDocument();
    expect(screen.getByText("Try a different search term")).toBeInTheDocument();
  });

  it("does not render primary navigation links (those live in the shared app sidebar)", () => {
    renderSidebar();

    expect(screen.queryByRole("link", { name: "Kanban" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Dashboard" })).toBeNull();
  });

  it("resumes the matching session when its card is clicked", async () => {
    const user = userEvent.setup();
    const props = renderSidebar();

    await user.click(screen.getByText("Planning session"));
    expect(props.onResumeSession).toHaveBeenCalledWith("session-1");
  });

  it("renders the session card as a link to support browser tab actions", () => {
    renderSidebar();

    expect(screen.getByRole("link", { name: /Planning session/i })).toHaveAttribute(
      "href",
      "/sessions/session-1",
    );
  });

  it("keeps the actions menu separate from session navigation", async () => {
    const user = userEvent.setup();
    const props = renderSidebar();

    await user.click(screen.getByRole("button", { name: "Open actions for Planning session" }));
    expect(props.onResumeSession).not.toHaveBeenCalled();

    await user.click(await screen.findByRole("menuitem", { name: /delete/i }));

    expect(props.onDeleteSession).toHaveBeenCalledWith(props.sessions[0]);
    expect(props.onResumeSession).not.toHaveBeenCalled();
  });

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
