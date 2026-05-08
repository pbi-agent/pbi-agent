import userEvent from "@testing-library/user-event";
import { act, screen } from "@testing-library/react";
import { vi } from "vitest";
import { renderWithProviders } from "../test/render";
import { useSettingsDialog } from "../hooks/useSettingsDialog";
import { useSidebarStore } from "../hooks/useSidebar";
import type { BootstrapPayload, ConfigBootstrapPayload } from "../types";

const mocks = vi.hoisted(() => ({
  fetchBootstrap: vi.fn(),
  fetchConfigBootstrap: vi.fn(),
}));

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchBootstrap: mocks.fetchBootstrap,
    fetchConfigBootstrap: mocks.fetchConfigBootstrap,
  };
});

vi.mock("../hooks/useTaskEvents", () => ({
  useTaskEvents: () => [],
}));

vi.doMock("./session/SessionPage", () => ({
  SessionPage: () => <div>Session Page</div>,
}));

vi.doMock("./board/BoardPage", () => ({
  BoardPage: () => <div>Board Page</div>,
}));

vi.doMock("./settings/SettingsPage", () => ({
  SettingsPage: () => <div>Settings Page</div>,
}));

vi.doMock("./dashboard/DashboardPage", () => ({
  DashboardPage: () => <div>Dashboard Page</div>,
}));

class MockEventSource {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {}

  close = vi.fn();
}

vi.stubGlobal("EventSource", MockEventSource);
Element.prototype.scrollTo = vi.fn();

const { AppShell } = await import("./AppShell");
const { fetchBootstrap, fetchConfigBootstrap } = mocks;

function makeBootstrap(): BootstrapPayload {
  return {
    workspace_root: "/workspace/demo",
    workspace_key: "/workspace/demo",
    workspace_display_path: "/workspace/demo",
    is_sandbox: false,
    provider: null,
    provider_id: null,
    profile_id: null,
    model: null,
    reasoning_effort: null,
    supports_image_inputs: true,
    sessions: [],
    tasks: [],
    live_sessions: [],
    board_stages: [],
  };
}

function makeConfigBootstrap(
  overrides: Partial<ConfigBootstrapPayload> = {},
): ConfigBootstrapPayload {
  return {
    config_revision: "rev-1",
    active_profile_id: "profile-1",
    providers: [],
    model_profiles: [
      {
        id: "profile-1",
        name: "Default",
        provider_id: "chatgpt",
        provider: { id: "chatgpt", name: "ChatGPT", kind: "chatgpt" },
        model: "gpt-5.4",
        sub_agent_model: null,
        reasoning_effort: "medium",
        max_tokens: null,
        service_tier: null,
        web_search: null,
        max_tool_workers: null,
        max_retries: null,
        compact_threshold: null,
        compact_tail_turns: null,
        compact_preserve_recent_tokens: null,
        compact_tool_output_max_chars: null,
        is_active_default: true,
        resolved_runtime: {} as ConfigBootstrapPayload["model_profiles"][number]["resolved_runtime"],
      },
    ],
    commands: [],
    options: {
      provider_kinds: ["chatgpt"],
      reasoning_efforts: ["medium"],
      openai_service_tiers: [],
      provider_metadata: {
        chatgpt: {
          label: "ChatGPT (Subscription)",
          description: "Uses your ChatGPT subscription account.",
          default_auth_mode: "chatgpt_account",
          auth_modes: ["chatgpt_account"],
          auth_mode_metadata: {
            chatgpt_account: {
              label: "ChatGPT account",
              account_label: "ChatGPT subscription account",
              supported_methods: ["browser", "device"],
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

describe("AppShell", () => {
  beforeEach(() => {
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap());
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(makeConfigBootstrap());
    act(() => {
      useSidebarStore.setState({ isOpen: true });
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    act(() => {
      useSettingsDialog.setState({ open: false });
    });
  });

  it("renders the unified sidebar with primary navigation and a settings entry", async () => {
    const user = userEvent.setup();

    renderWithProviders(<AppShell />, { route: "/board" });

    const sidebar = await screen.findByRole("complementary", { name: "Application sidebar" });
    expect(sidebar).toBeInTheDocument();

    const sidebarNav = await screen.findByRole("navigation", { name: "Primary navigation" });
    expect(sidebarNav).toHaveTextContent("Sessions");
    expect(sidebarNav).toHaveTextContent("Kanban");
    expect(sidebarNav).toHaveTextContent("Dashboard");

    expect(screen.getByRole("link", { name: "Sessions" })).toHaveAttribute("href", "/sessions");
    expect(screen.getByRole("link", { name: "Kanban" })).toHaveAttribute("href", "/board");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/dashboard");

    expect(screen.queryByRole("banner")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Settings" }));
    expect(useSettingsDialog.getState().open).toBe(true);
  });

  it("shows the app sidebar around dashboard pages", async () => {
    renderWithProviders(<AppShell />, { route: "/dashboard" });

    expect(await screen.findByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sessions" })).toHaveAttribute("href", "/sessions");
  });

  it("does not render the theme menu button in the sidebar footer", async () => {
    renderWithProviders(<AppShell />, { route: "/board" });

    await screen.findByRole("button", { name: "Settings" });
    expect(screen.queryByRole("button", { name: "Change theme" })).not.toBeInTheDocument();
  });

  it("redirects /settings to the sessions route", async () => {
    renderWithProviders(<AppShell />, {
      route: "/settings",
    });

    expect(await screen.findByText("Session Page")).toBeInTheDocument();
  });

  it("hides the workspace badge prefix when the workspace path is sandboxed", async () => {
    vi.mocked(fetchBootstrap).mockResolvedValue({
      ...makeBootstrap(),
      workspace_root: "/workspace/d0918d973e2e241d",
      workspace_key: "/Users/ada/project",
      workspace_display_path: "/Users/ada/project",
      is_sandbox: true,
    });

    renderWithProviders(<AppShell />, { route: "/board" });

    expect(await screen.findByRole("button", { name: "Settings" })).toBeInTheDocument();
    expect(screen.queryByText("workspace/d0918d973e2e241d")).not.toBeInTheDocument();
  });

  it("toggles the sidebar collapse state when Ctrl+B is pressed", async () => {
    const user = userEvent.setup();

    renderWithProviders(<AppShell />, { route: "/board" });

    await screen.findByRole("navigation", { name: "Primary navigation" });
    expect(useSidebarStore.getState().isOpen).toBe(true);

    await user.keyboard("{Control>}b{/Control}");
    expect(useSidebarStore.getState().isOpen).toBe(false);

    await user.keyboard("{Control>}b{/Control}");
    expect(useSidebarStore.getState().isOpen).toBe(true);
  });

  it("ignores the shortcut when shift or alt modifiers are held", async () => {
    const user = userEvent.setup();

    renderWithProviders(<AppShell />, { route: "/board" });

    await screen.findByRole("navigation", { name: "Primary navigation" });
    expect(useSidebarStore.getState().isOpen).toBe(true);

    await user.keyboard("{Control>}{Shift>}b{/Shift}{/Control}");
    expect(useSidebarStore.getState().isOpen).toBe(true);

    await user.keyboard("{Control>}{Alt>}b{/Alt}{/Control}");
    expect(useSidebarStore.getState().isOpen).toBe(true);
  });

  it("toggles the sidebar from the head toggle button", async () => {
    const user = userEvent.setup();

    renderWithProviders(<AppShell />, { route: "/board" });

    expect(useSidebarStore.getState().isOpen).toBe(true);
    await user.click(await screen.findByRole("button", { name: "Collapse sidebar" }));
    expect(useSidebarStore.getState().isOpen).toBe(false);

    await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(useSidebarStore.getState().isOpen).toBe(true);
  });
});
