import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { SettingsPage } from "./SettingsPage";
import { renderWithProviders } from "../../test/render";
import {
  ApiError,
  fetchConfigBootstrap,
  fetchProviderAuthFlow,
  logoutProviderAuth,
  refreshProviderAuth,
  setActiveModelProfile,
  startProviderAuthFlow,
} from "../../api";
import type { ConfigBootstrapPayload } from "../../types";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    fetchConfigBootstrap: vi.fn(),
    createProvider: vi.fn(),
    updateProvider: vi.fn(),
    deleteProvider: vi.fn(),
    createModelProfile: vi.fn(),
    updateModelProfile: vi.fn(),
    deleteModelProfile: vi.fn(),
    setActiveModelProfile: vi.fn(),
    startProviderAuthFlow: vi.fn(),
    fetchProviderAuthFlow: vi.fn(),
    refreshProviderAuth: vi.fn(),
    logoutProviderAuth: vi.fn(),
  };
});

function makeConfigBootstrap(
  overrides: Partial<ConfigBootstrapPayload> = {},
): ConfigBootstrapPayload {
  return {
    config_revision: "rev-1",
    active_profile_id: "analysis",
    providers: [
      {
        id: "openai-main",
        name: "OpenAI Main",
        kind: "openai",
        auth_mode: "api_key",
        responses_url: null,
        generic_api_url: null,
        secret_source: "env_var",
        secret_env_var: "OPENAI_API_KEY",
        has_secret: true,
        auth_status: {
          auth_mode: "api_key",
          backend: null,
          session_status: "missing",
          has_session: false,
          can_refresh: false,
          account_id: null,
          email: null,
          plan_type: null,
          expires_at: null,
        },
      },
      {
        id: "openai-chatgpt",
        name: "OpenAI ChatGPT",
        kind: "openai",
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
    model_profiles: [
      {
        id: "analysis",
        name: "Analysis",
        provider_id: "openai-main",
        provider: { id: "openai-main", name: "OpenAI Main", kind: "openai" },
        model: "gpt-5.4",
        sub_agent_model: null,
        reasoning_effort: "high",
        max_tokens: null,
        service_tier: null,
        web_search: false,
        max_tool_workers: null,
        max_retries: null,
        compact_threshold: null,
        is_active_default: true,
        resolved_runtime: {
          provider: "OpenAI",
          provider_id: "openai-main",
          profile_id: "analysis",
          model: "gpt-5.4",
          sub_agent_model: null,
          reasoning_effort: "high",
          max_tokens: 0,
          service_tier: null,
          web_search: false,
          max_tool_workers: 1,
          max_retries: 1,
          compact_threshold: 1,
          responses_url: "https://api.openai.com/v1/responses",
          generic_api_url: "https://api.openai.com/v1/chat/completions",
          supports_image_inputs: true,
        },
      },
      {
        id: "qa",
        name: "QA",
        provider_id: "openai-main",
        provider: { id: "openai-main", name: "OpenAI Main", kind: "openai" },
        model: "gpt-5.4-mini",
        sub_agent_model: null,
        reasoning_effort: "medium",
        max_tokens: null,
        service_tier: null,
        web_search: false,
        max_tool_workers: null,
        max_retries: null,
        compact_threshold: null,
        is_active_default: false,
        resolved_runtime: {
          provider: "OpenAI",
          provider_id: "openai-main",
          profile_id: "qa",
          model: "gpt-5.4-mini",
          sub_agent_model: null,
          reasoning_effort: "medium",
          max_tokens: 0,
          service_tier: null,
          web_search: false,
          max_tool_workers: 1,
          max_retries: 1,
          compact_threshold: 1,
          responses_url: "https://api.openai.com/v1/responses",
          generic_api_url: "https://api.openai.com/v1/chat/completions",
          supports_image_inputs: true,
        },
      },
    ],
    commands: [],
    options: {
      provider_kinds: ["openai"],
      reasoning_efforts: ["high", "medium"],
      openai_service_tiers: [],
      provider_metadata: {
        openai: {
          default_auth_mode: "api_key",
          auth_modes: ["api_key", "chatgpt_account"],
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

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(makeConfigBootstrap());
    vi.mocked(setActiveModelProfile).mockResolvedValue({
      active_profile_id: "qa",
      config_revision: "rev-2",
    });
    vi.mocked(startProviderAuthFlow).mockResolvedValue({
      provider: makeConfigBootstrap().providers[1],
      auth_status: makeConfigBootstrap().providers[1].auth_status,
      flow: {
        flow_id: "flow-1",
        provider_id: "openai-chatgpt",
        backend: "openai-chatgpt",
        method: "browser",
        status: "pending",
        authorization_url: "https://chatgpt.com/auth",
        callback_url: "http://localhost/callback",
        verification_url: null,
        user_code: null,
        interval_seconds: 1,
        error_message: null,
        created_at: "2026-04-16T00:00:00Z",
        updated_at: "2026-04-16T00:00:00Z",
      },
      session: null,
    });
    vi.mocked(fetchProviderAuthFlow).mockResolvedValue({
      provider: {
        ...makeConfigBootstrap().providers[1],
        auth_status: {
          ...makeConfigBootstrap().providers[1].auth_status,
          session_status: "connected",
          has_session: true,
          email: "user@example.com",
          plan_type: "Plus",
          expires_at: 1_800_000_000,
        },
      },
      auth_status: {
        ...makeConfigBootstrap().providers[1].auth_status,
        session_status: "connected",
        has_session: true,
        email: "user@example.com",
        plan_type: "Plus",
        expires_at: 1_800_000_000,
      },
      flow: {
        flow_id: "flow-1",
        provider_id: "openai-chatgpt",
        backend: "openai-chatgpt",
        method: "browser",
        status: "completed",
        authorization_url: "https://chatgpt.com/auth",
        callback_url: "http://localhost/callback",
        verification_url: null,
        user_code: null,
        interval_seconds: 1,
        error_message: null,
        created_at: "2026-04-16T00:00:00Z",
        updated_at: "2026-04-16T00:00:02Z",
      },
      session: {
        provider_id: "openai-chatgpt",
        backend: "openai-chatgpt",
        expires_at: 1_800_000_000,
        account_id: "acct-1",
        email: "user@example.com",
        plan_type: "Plus",
      },
    });
    vi.mocked(refreshProviderAuth).mockResolvedValue({
      provider: makeConfigBootstrap().providers[1],
      auth_status: {
        ...makeConfigBootstrap().providers[1].auth_status,
        session_status: "connected",
        has_session: true,
        can_refresh: true,
      },
      session: {
        provider_id: "openai-chatgpt",
        backend: "openai-chatgpt",
        expires_at: 1_800_000_000,
        account_id: "acct-1",
        email: "user@example.com",
        plan_type: "Plus",
      },
    });
    vi.mocked(logoutProviderAuth).mockResolvedValue({
      provider: makeConfigBootstrap().providers[1],
      auth_status: makeConfigBootstrap().providers[1].auth_status,
      removed: true,
    });
    vi.spyOn(window, "open").mockImplementation(() => null);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("renders the onboarding and empty-provider states when config is blank", async () => {
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        providers: [],
        model_profiles: [],
        active_profile_id: null,
      }),
    );

    renderWithProviders(<SettingsPage />);

    expect(await screen.findByText(/First-time setup:/)).toBeInTheDocument();
    expect(screen.getByText("No providers configured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ Add Profile" })).toBeDisabled();
  });

  it("updates the active default profile through the API", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await user.selectOptions(await screen.findByRole("combobox"), "qa");

    await waitFor(() =>
      expect(setActiveModelProfile).toHaveBeenCalledWith("qa", "rev-1"),
    );
  });

  it("shows provider auth controls and starts the browser auth flow", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderWithProviders(<SettingsPage />);

    expect(await screen.findByText("OpenAI ChatGPT")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Connect" })[0]);

    expect(await screen.findByText("Connect ChatGPT account")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start browser sign-in" }));

    expect(startProviderAuthFlow).toHaveBeenCalledWith("openai-chatgpt", "browser");
    expect(window.open).toHaveBeenCalledWith(
      "https://chatgpt.com/auth",
      "_blank",
      "noopener,noreferrer",
    );

    await user.click(screen.getByRole("button", { name: "Check status" }));

    await waitFor(() =>
      expect(fetchProviderAuthFlow).toHaveBeenCalledWith(
        "openai-chatgpt",
        "flow-1",
      ),
    );
    await waitFor(() =>
      expect(queryClient.isFetching({ queryKey: ["config-bootstrap"] })).toBe(0),
    );
    expect(await screen.findByText(/Connected as user@example.com/)).toBeInTheDocument();
  });

  it("refreshes settings after a manual auth status check completes the flow", async () => {
    const user = userEvent.setup();
    const refreshedBootstrap = makeConfigBootstrap({
      providers: [
        {
          ...makeConfigBootstrap().providers[0],
        },
        {
          ...makeConfigBootstrap().providers[1],
          auth_status: {
            ...makeConfigBootstrap().providers[1].auth_status,
            session_status: "connected",
            has_session: true,
            can_refresh: true,
            email: "user@example.com",
            plan_type: "plus",
          },
        },
      ],
    });
    vi.mocked(fetchConfigBootstrap)
      .mockResolvedValueOnce(makeConfigBootstrap())
      .mockResolvedValueOnce(refreshedBootstrap)
      .mockResolvedValue(refreshedBootstrap);

    renderWithProviders(<SettingsPage />);

    expect(await screen.findByText("OpenAI ChatGPT")).toBeInTheDocument();
    expect(screen.getByText("not connected")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Connect" })[0]);
    await user.click(screen.getByRole("button", { name: "Start browser sign-in" }));
    await user.click(screen.getByRole("button", { name: "Check status" }));

    expect(await screen.findByText(/Connected as user@example.com/)).toBeInTheDocument();
    expect(await screen.findByText("connected")).toBeInTheDocument();
    expect(fetchConfigBootstrap).toHaveBeenCalledTimes(2);
  });

  it("allows closing the auth modal while completion refresh is still in flight", async () => {
    const user = userEvent.setup();
    let resolveRefresh!: (value: ConfigBootstrapPayload) => void;
    const pendingRefresh = new Promise<ConfigBootstrapPayload>((resolve) => {
      resolveRefresh = resolve;
    });
    vi.mocked(fetchConfigBootstrap)
      .mockResolvedValueOnce(makeConfigBootstrap())
      .mockReturnValueOnce(pendingRefresh)
      .mockResolvedValue(makeConfigBootstrap());

    renderWithProviders(<SettingsPage />);

    expect(await screen.findByText("OpenAI ChatGPT")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Connect" })[0]);
    await user.click(screen.getByRole("button", { name: "Start browser sign-in" }));
    await user.click(screen.getByRole("button", { name: "Check status" }));

    expect(await screen.findByText(/Connected as user@example.com/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() =>
      expect(screen.queryByText("Connect ChatGPT account")).not.toBeInTheDocument(),
    );

    resolveRefresh(makeConfigBootstrap());
  });

  it("refreshes and disconnects provider auth from the provider card", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        providers: [
          makeConfigBootstrap().providers[0],
          {
            ...makeConfigBootstrap().providers[1],
            auth_status: {
              ...makeConfigBootstrap().providers[1].auth_status,
              session_status: "connected",
              has_session: true,
              can_refresh: true,
            },
          },
        ],
      }),
    );

    renderWithProviders(<SettingsPage />);

    await screen.findByText("OpenAI ChatGPT");
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() =>
      expect(refreshProviderAuth).toHaveBeenCalledWith("openai-chatgpt"),
    );

    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    await waitFor(() =>
      expect(logoutProviderAuth).toHaveBeenCalledWith("openai-chatgpt"),
    );
  });

  it("shows the stale-config banner when the active profile update conflicts", async () => {
    const user = userEvent.setup();
    vi.mocked(setActiveModelProfile).mockRejectedValue(
      new ApiError("Config has changed on disk.", 409),
    );

    renderWithProviders(<SettingsPage />);

    await user.selectOptions(await screen.findByRole("combobox"), "qa");

    expect(
      await screen.findByText(
        "Settings were changed while you were editing. Please review and resubmit.",
      ),
    ).toBeInTheDocument();
  });

  it("renders a settings load error when bootstrap fails", async () => {
    vi.mocked(fetchConfigBootstrap).mockRejectedValue(new Error("boom"));

    renderWithProviders(<SettingsPage />);

    expect(await screen.findByText(/Failed to load settings:/)).toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
});
