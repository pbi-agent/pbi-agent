import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import { AppSessionsContextPanel } from "./AppSessionsContextPanel";
import type { SessionRecord } from "../types";

const mocks = vi.hoisted(() => ({
  fetchSessions: vi.fn(),
  updateSession: vi.fn(),
  deleteSession: vi.fn(),
}));

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchSessions: mocks.fetchSessions,
    updateSession: mocks.updateSession,
    deleteSession: mocks.deleteSession,
  };
});

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

function renderPanel(route = "/board") {
  return renderWithProviders(
    <Routes>
      <Route path="/board" element={<AppSessionsContextPanel />} />
      <Route
        path="/sessions/:sessionId"
        element={<AppSessionsContextPanel />}
      />
      <Route path="/sessions" element={<AppSessionsContextPanel />} />
    </Routes>,
    { route },
  );
}

describe("AppSessionsContextPanel", () => {
  beforeEach(() => {
    mocks.fetchSessions.mockResolvedValue([makeSession()]);
    mocks.updateSession.mockResolvedValue(makeSession({ title: "Renamed" }));
    mocks.deleteSession.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the sessions list with the Sessions section header", async () => {
    renderPanel();

    expect(
      await screen.findByRole("heading", { name: "Sessions" }),
    ).toBeInTheDocument();
    await screen.findByText("Planning session");
  });

  it("renames a session through the inline edit form", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(
      await screen.findByRole("button", {
        name: "Open actions for Planning session",
      }),
    );
    await user.click(await screen.findByRole("menuitem", { name: /edit title/i }));

    const input = screen.getByLabelText("Session title");
    await user.clear(input);
    await user.type(input, "Renamed");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(mocks.updateSession).toHaveBeenCalledWith("session-1", {
        title: "Renamed",
      });
    });
  });

  it("opens the delete confirmation dialog from the row menu", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(
      await screen.findByRole("button", {
        name: "Open actions for Planning session",
      }),
    );
    await user.click(await screen.findByRole("menuitem", { name: /delete/i }));

    expect(
      await screen.findByRole("heading", { name: /delete session/i }),
    ).toBeInTheDocument();
  });
});
