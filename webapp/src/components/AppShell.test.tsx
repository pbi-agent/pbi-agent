import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { AppShell } from "./AppShell";
import { renderWithProviders } from "../test/render";
import { fetchBootstrap, fetchConfigBootstrap } from "../api";
import type { BootstrapPayload, ConfigBootstrapPayload } from "../types";

vi.mock("./session/SessionPage", () => ({
  SessionPage: () => <div>Session Page</div>,
}));

vi.mock("./board/BoardPage", () => ({
  BoardPage: () => <div>Board Page</div>,
}));

vi.mock("./settings/SettingsPage", () => ({
  SettingsPage: () => <div>Settings Page</div>,
}));

vi.mock("./dashboard/DashboardPage", () => ({
  DashboardPage: () => <div>Dashboard Page</div>,
}));

vi.mock("../hooks/useTaskEvents", () => ({
  useTaskEvents: vi.fn(),
}));

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchBootstrap: vi.fn(),
    fetchConfigBootstrap: vi.fn(),
  };
});

function makeBootstrap(): BootstrapPayload {
  return {
    workspace_root: "/workspace/demo",
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
    active_profile_id: null,
    providers: [],
    model_profiles: [],
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
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("keeps onboarding dismissed on settings while config revisions change during setup", async () => {
    const user = userEvent.setup();
    const nextConfig = makeConfigBootstrap({
      config_revision: "rev-2",
      providers: [
        {
          id: "chatgpt-main",
          name: "ChatGPT Main",
          kind: "chatgpt",
          auth_mode: "chatgpt_account",
          responses_url: null,
          generic_api_url: null,
          secret_source: "none",
          secret_env_var: null,
          has_secret: false,
          auth_status: {
            auth_mode: "chatgpt_account",
            backend: "openai-chatgpt",
            session_status: "missing",
            has_session: false,
            can_refresh: false,
            account_id: null,
            email: null,
            plan_type: null,
            expires_at: null,
          },
        },
      ],
    });
    vi.mocked(fetchConfigBootstrap)
      .mockResolvedValueOnce(makeConfigBootstrap())
      .mockResolvedValueOnce(nextConfig)
      .mockResolvedValue(nextConfig);

    const { queryClient } = renderWithProviders(<AppShell />, {
      route: "/settings",
    });

    expect(await screen.findByText("Setup Required")).toBeInTheDocument();
    expect(await screen.findByText("Settings Page")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Configure below" }));

    await waitFor(() =>
      expect(screen.queryByText("Setup Required")).not.toBeInTheDocument(),
    );

    await queryClient.invalidateQueries({ queryKey: ["config-bootstrap"] });

    await waitFor(() => expect(fetchConfigBootstrap).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Setup Required")).not.toBeInTheDocument();
  });
});
