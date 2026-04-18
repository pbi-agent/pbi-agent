import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { SettingsPage } from "./SettingsPage";
import { renderWithProviders } from "../../test/render";
import {
  ApiError,
  fetchConfigBootstrap,
  fetchProviderModels,
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
    fetchProviderModels: vi.fn(),
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
    vi.mocked(fetchProviderModels).mockResolvedValue({
      provider_id: "openai-main",
      provider_kind: "openai",
      discovery_supported: true,
      manual_entry_required: false,
      models: [
        {
          id: "gpt-5.4",
          display_name: "GPT-5.4",
          created: 1_713_000_000,
          owned_by: "openai",
          input_modalities: ["text"],
          output_modalities: ["text"],
          aliases: [],
          supports_reasoning_effort: true,
        },
        {
          id: "gpt-5.4-mini",
          display_name: "GPT-5.4 mini",
          created: 1_713_000_100,
          owned_by: "openai",
          input_modalities: ["text"],
          output_modalities: ["text"],
          aliases: ["gpt-5-mini"],
          supports_reasoning_effort: true,
        },
      ],
      error: null,
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

  it("fetches provider models when the profile modal opens and when the provider changes", async () => {
    const user = userEvent.setup();
    const bootstrap = makeConfigBootstrap({
      providers: [
        ...makeConfigBootstrap().providers,
        {
          id: "xai-main",
          name: "xAI Main",
          kind: "xai",
          auth_mode: "api_key",
          responses_url: null,
          generic_api_url: null,
          secret_source: "env_var",
          secret_env_var: "XAI_API_KEY",
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
      ],
      options: {
        ...makeConfigBootstrap().options,
        provider_kinds: ["openai", "xai"],
        provider_metadata: {
          ...makeConfigBootstrap().options.provider_metadata,
          xai: {
            default_auth_mode: "api_key",
            auth_modes: ["api_key"],
            default_model: "grok-4.20",
            default_sub_agent_model: "grok-4.1-fast",
            default_responses_url: "https://api.x.ai/v1/responses",
            default_generic_api_url: null,
            supports_responses_url: true,
            supports_generic_api_url: false,
            supports_service_tier: false,
            supports_native_web_search: true,
            supports_image_inputs: false,
          },
        },
      },
    });
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(bootstrap);
    vi.mocked(fetchProviderModels)
      .mockResolvedValueOnce({
        provider_id: "openai-main",
        provider_kind: "openai",
        discovery_supported: true,
        manual_entry_required: false,
        models: [],
        error: null,
      })
      .mockResolvedValueOnce({
        provider_id: "xai-main",
        provider_kind: "xai",
        discovery_supported: true,
        manual_entry_required: false,
        models: [],
        error: null,
      });

    const { container } = renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "+ Add Profile" }));
    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("openai-main"),
    );

    const providerSelect = container.querySelector(
      'select[name="provider-id"]',
    ) as HTMLSelectElement;
    await user.selectOptions(providerSelect, "xai-main");

    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("xai-main"),
    );
  });

  it("renders fetched provider models as dropdowns in the profile modal", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "+ Add Profile" }));

    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("openai-main"),
    );

    const modelSelect = container.querySelector('select[name="model"]');
    const subAgentModelSelect = container.querySelector(
      'select[name="sub-agent-model"]',
    );
    expect(modelSelect).not.toBeNull();
    expect(subAgentModelSelect).not.toBeNull();
    expect(
      screen.getAllByRole("option", { name: "GPT-5.4 (gpt-5.4)" }),
    ).toHaveLength(2);
    expect(
      screen.getAllByRole("option", { name: "GPT-5.4 mini (gpt-5.4-mini)" }),
    ).toHaveLength(2);
  });

  it("falls back to text input when provider model discovery fails", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchProviderModels).mockResolvedValue({
      provider_id: "openai-main",
      provider_kind: "openai",
      discovery_supported: true,
      manual_entry_required: true,
      models: [],
      error: {
        code: "auth_required",
        message: "Missing authentication for provider 'openai'.",
        status_code: null,
      },
    });

    const { container } = renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "+ Add Profile" }));

    await screen.findByText("Missing authentication for provider 'openai'.");
    expect(container.querySelector('input[name="model"]')).not.toBeNull();
    expect(container.querySelector('select[name="model"]')).toBeNull();
  });

  it("keeps an existing unknown model editable when discovery does not return it", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        model_profiles: [
          {
            ...makeConfigBootstrap().model_profiles[0],
            id: "legacy",
            name: "Legacy",
            model: "legacy-model",
            sub_agent_model: "legacy-sub-agent",
          },
        ],
      }),
    );

    const { container } = renderWithProviders(<SettingsPage />);

    await screen.findByRole("button", { name: "+ Add Profile" });
    await user.click(screen.getAllByRole("button", { name: "Edit" })[2]);

    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("openai-main"),
    );

    const modelInput = container.querySelector(
      'input[name="model"]',
    ) as HTMLInputElement | null;
    const subAgentModelInput = container.querySelector(
      'input[name="sub-agent-model"]',
    ) as HTMLInputElement | null;
    expect(modelInput?.value).toBe("legacy-model");
    expect(subAgentModelInput?.value).toBe("legacy-sub-agent");
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
