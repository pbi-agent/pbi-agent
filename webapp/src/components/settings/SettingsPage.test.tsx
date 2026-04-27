import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { SettingsPage } from "./SettingsPage";
import { renderWithProviders } from "../../test/render";
import {
  ApiError,
  createProvider,
  createModelProfile,
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
      provider_kinds: ["openai", "chatgpt", "github_copilot"],
      reasoning_efforts: ["high", "medium"],
      openai_service_tiers: [],
      provider_metadata: {
        openai: {
          label: "OpenAI API",
          description: "Uses an OpenAI API key.",
          default_auth_mode: "api_key",
          auth_modes: ["api_key"],
          auth_mode_metadata: {
            api_key: {
              label: "API key",
              account_label: null,
              supported_methods: [],
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
        azure: {
          label: "Azure",
          description:
            "Uses an Azure API key and resource-specific Responses URL. Model names are Azure deployment names.",
          default_auth_mode: "api_key",
          auth_modes: ["api_key"],
          auth_mode_metadata: {
            api_key: {
              label: "API key",
              account_label: null,
              supported_methods: [],
            },
          },
          default_model: "gpt-4.1",
          default_sub_agent_model: "gpt-4.1-mini",
          default_responses_url: "",
          default_generic_api_url: null,
          supports_responses_url: true,
          supports_generic_api_url: false,
          supports_service_tier: false,
          supports_native_web_search: true,
          supports_image_inputs: true,
        },
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
        github_copilot: {
          label: "GitHub Copilot (Subscription)",
          description: "Uses your GitHub Copilot subscription account.",
          default_auth_mode: "copilot_account",
          auth_modes: ["copilot_account"],
          auth_mode_metadata: {
            copilot_account: {
              label: "GitHub Copilot account",
              account_label: "GitHub Copilot subscription account",
              supported_methods: ["device"],
            },
          },
          default_model: "gpt-5.4",
          default_sub_agent_model: "gpt-5-mini",
          default_responses_url: "https://api.githubcopilot.com/responses",
          default_generic_api_url: null,
          supports_responses_url: true,
          supports_generic_api_url: false,
          supports_service_tier: false,
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
    vi.mocked(createProvider).mockResolvedValue({
      provider: {
        id: "chatgpt-new",
        name: "ChatGPT New",
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
      config_revision: "rev-2",
    });
    vi.mocked(setActiveModelProfile).mockResolvedValue({
      active_profile_id: "qa",
      config_revision: "rev-2",
    });
    vi.mocked(startProviderAuthFlow).mockResolvedValue({
      provider: makeConfigBootstrap().providers[1],
      auth_status: makeConfigBootstrap().providers[1].auth_status,
      flow: {
        flow_id: "flow-1",
        provider_id: "chatgpt-main",
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
        provider_id: "chatgpt-main",
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
        provider_id: "chatgpt-main",
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
        provider_id: "chatgpt-main",
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
    expect(screen.getByRole("button", { name: "Add Profile" })).toBeDisabled();
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

    expect(await screen.findByText("ChatGPT Main")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Connect" })[0]);

    expect(await screen.findByText("Connect ChatGPT account")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start browser sign-in" }));

    expect(startProviderAuthFlow).toHaveBeenCalledWith("chatgpt-main", "browser");
    expect(window.open).toHaveBeenCalledWith(
      "https://chatgpt.com/auth",
      "_blank",
      "noopener,noreferrer",
    );

    await user.click(screen.getByRole("button", { name: "Check status" }));

    await waitFor(() =>
      expect(fetchProviderAuthFlow).toHaveBeenCalledWith(
        "chatgpt-main",
        "flow-1",
      ),
    );
    await waitFor(() =>
      expect(queryClient.isFetching({ queryKey: ["config-bootstrap"] })).toBe(0),
    );
    expect(await screen.findByText(/Connected as user@example.com/)).toBeInTheDocument();
  });

  it("uses provider metadata to render a device-only Copilot auth flow", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        providers: [
          {
            id: "copilot-main",
            name: "Copilot Main",
            kind: "github_copilot",
            auth_mode: "copilot_account",
            responses_url: "https://api.githubcopilot.com/responses",
            generic_api_url: null,
            secret_source: "none",
            secret_env_var: null,
            has_secret: false,
            auth_status: {
              auth_mode: "copilot_account",
              backend: "github_copilot",
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
      }),
    );
    vi.mocked(startProviderAuthFlow).mockResolvedValue({
      provider: makeConfigBootstrap({
        providers: [
          {
            id: "copilot-main",
            name: "Copilot Main",
            kind: "github_copilot",
            auth_mode: "copilot_account",
            responses_url: "https://api.githubcopilot.com/responses",
            generic_api_url: null,
            secret_source: "none",
            secret_env_var: null,
            has_secret: false,
            auth_status: {
              auth_mode: "copilot_account",
              backend: "github_copilot",
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
      }).providers[0],
      auth_status: {
        auth_mode: "copilot_account",
        backend: "github_copilot",
        session_status: "missing",
        has_session: false,
        can_refresh: false,
        account_id: null,
        email: null,
        plan_type: null,
        expires_at: null,
      },
      flow: {
        flow_id: "copilot-flow-1",
        provider_id: "copilot-main",
        backend: "github_copilot",
        method: "device",
        status: "pending",
        authorization_url: null,
        callback_url: null,
        verification_url: "https://github.com/login/device",
        user_code: "ABCD-EFGH",
        interval_seconds: 5,
        error_message: null,
        created_at: "2026-04-18T00:00:00Z",
        updated_at: "2026-04-18T00:00:00Z",
      },
      session: null,
    });

    renderWithProviders(<SettingsPage />);

    expect(await screen.findByText("Copilot Main")).toBeInTheDocument();
    expect(screen.getByText("GitHub Copilot account")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Connect" }));

    expect(
      await screen.findByText("Connect GitHub Copilot account"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Authorize Copilot Main with your GitHub Copilot subscription account."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Method")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Generate device code" }));
    expect(startProviderAuthFlow).toHaveBeenCalledWith("copilot-main", "device");
  });

  it("uses the standard task form shell for the provider form", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Add Provider" }));

    const dialog = screen.getByRole("dialog", { name: "Add Provider" });
    expect(dialog).toHaveClass("task-form-dialog");
    expect(dialog.querySelector(".task-form__body")).not.toBeNull();
    expect(document.querySelector('input[name="provider-name"]')).toHaveClass(
      "task-form__input",
    );
    expect(document.querySelector('select[name="provider-kind"]')).toHaveClass(
      "task-form__select",
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass(
      "task-form__action-button",
    );
    expect(screen.getByRole("button", { name: "Add Provider" })).toHaveClass(
      "task-form__action-button",
    );
  });

  it("uses provider kind labels and descriptions in the provider form", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Add Provider" }));

    expect(screen.getAllByRole("option", { name: "OpenAI API" })[0]).toBeInTheDocument();
    expect(
      screen.getAllByRole("option", { name: "ChatGPT (Subscription)" })[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("option", { name: "GitHub Copilot (Subscription)" })[0],
    ).toBeInTheDocument();
    expect(screen.getByText("Uses an OpenAI API key.")).toBeInTheDocument();
  });

  it("configures Azure provider fields and saves the Azure URL", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        options: {
          ...makeConfigBootstrap().options,
          provider_kinds: ["openai", "azure", "chatgpt"],
        },
      }),
    );

    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Add Provider" }));
    await user.selectOptions(
      document.querySelector('select[name="provider-kind"]') as HTMLSelectElement,
      "azure",
    );

    expect(screen.getByText("Azure")).toBeInTheDocument();
    expect(screen.getByDisplayValue("AZURE_API_KEY")).toBeInTheDocument();
    expect(screen.getByText("Azure endpoint URL")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Required. Routes by URL: /openai/v1/responses, /openai/v1, or /anthropic/v1/messages.",
      ),
    ).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("e.g. My OpenAI"), "Azure Main");
    await user.type(
      screen.getByPlaceholderText(
        "https://<resource>.openai.azure.com/openai/v1/responses",
      ),
      "https://example-resource.openai.azure.com/openai/v1/responses",
    );
    await user.click(screen.getByRole("button", { name: "Add Provider" }));

    await waitFor(() =>
      expect(createProvider).toHaveBeenCalledWith(
        {
          name: "Azure Main",
          kind: "azure",
          auth_mode: "api_key",
          api_key: null,
          api_key_env: "AZURE_API_KEY",
          responses_url:
            "https://example-resource.openai.azure.com/openai/v1/responses",
          generic_api_url: null,
        },
        "rev-1",
      ),
    );
  });

  it("opens provider auth immediately after creating a subscription-backed provider", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Add Provider" }));
    await user.selectOptions(
      document.querySelector('select[name="provider-kind"]') as HTMLSelectElement,
      "chatgpt",
    );
    await user.type(screen.getByPlaceholderText("e.g. My OpenAI"), "ChatGPT Starter");

    expect(
      screen.getByText(
        "Save this provider to continue directly into sign-in for your ChatGPT subscription account.",
      ),
    ).toBeInTheDocument();

    vi.mocked(createProvider).mockResolvedValueOnce({
      provider: {
        id: "chatgpt-starter",
        name: "ChatGPT Starter",
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
      config_revision: "rev-2",
    });

    await user.click(screen.getByRole("button", { name: "Add Provider" }));

    await waitFor(() =>
      expect(createProvider).toHaveBeenCalledWith(
        {
          name: "ChatGPT Starter",
          kind: "chatgpt",
          auth_mode: "chatgpt_account",
          api_key: null,
          api_key_env: null,
          responses_url: null,
          generic_api_url: null,
        },
        "rev-1",
      ),
    );
    expect(await screen.findByText("Connect ChatGPT account")).toBeInTheDocument();
    expect(
      screen.getByText("Authorize ChatGPT Starter with your ChatGPT subscription account."),
    ).toBeInTheDocument();
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

    expect(await screen.findByText("ChatGPT Main")).toBeInTheDocument();
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

    expect(await screen.findByText("ChatGPT Main")).toBeInTheDocument();
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

    await screen.findByText("ChatGPT Main");
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() =>
      expect(refreshProviderAuth).toHaveBeenCalledWith("chatgpt-main"),
    );

    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    await waitFor(() =>
      expect(logoutProviderAuth).toHaveBeenCalledWith("chatgpt-main"),
    );
  });

  it("fetches provider models when the profile modal opens and when the provider changes", async () => {
    const user = userEvent.setup();
    const bootstrap = makeConfigBootstrap({
      providers: [
        ...makeConfigBootstrap().providers,
        {
          id: "azure-main",
          name: "Azure Main",
          kind: "azure",
          auth_mode: "api_key",
          responses_url:
            "https://example-resource.openai.azure.com/openai/v1/responses",
          generic_api_url: null,
          secret_source: "env_var",
          secret_env_var: "AZURE_API_KEY",
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
        provider_kinds: ["openai", "azure", "xai"],
        provider_metadata: {
          ...makeConfigBootstrap().options.provider_metadata,
          xai: {
            label: "xAI",
            description: "Uses an xAI API key.",
            default_auth_mode: "api_key",
            auth_modes: ["api_key"],
            auth_mode_metadata: {
              api_key: {
                label: "API key",
                account_label: null,
                supported_methods: [],
              },
            },
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
      })
      .mockResolvedValueOnce({
        provider_id: "azure-main",
        provider_kind: "azure",
        discovery_supported: false,
        manual_entry_required: true,
        models: [],
        error: null,
      });

    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Add Profile" }));
    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("openai-main"),
    );

    const providerSelect = document.querySelector(
      'select[name="provider-id"]',
    ) as HTMLSelectElement;
    await user.selectOptions(providerSelect, "xai-main");

    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("xai-main"),
    );

    await user.selectOptions(providerSelect, "azure-main");

    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("azure-main"),
    );
    expect(
      screen.getByText(
        "Enter your Azure deployment name. Model discovery is not available for Azure — use a custom value.",
      ),
    ).toBeInTheDocument();
  });

  it("uses the standard task form shell for the profile form", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Add Profile" }));

    const dialog = screen.getByRole("dialog", { name: "Add Profile" });
    expect(dialog).toHaveClass("task-form-dialog");
    expect(dialog.querySelector(".task-form__body")).not.toBeNull();
    expect(document.querySelector('input[name="profile-name"]')).toHaveClass(
      "task-form__input",
    );
    expect(document.querySelector('select[name="provider-id"]')).toHaveClass(
      "task-form__select",
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass(
      "task-form__action-button",
    );
    expect(screen.getByRole("button", { name: "Add Profile" })).toHaveClass(
      "task-form__action-button",
    );
  });

  it("renders fetched provider models as dropdowns in the profile modal", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Add Profile" }));

    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("openai-main"),
    );

    const modelSelect = document.querySelector('select[name="model"]');
    const subAgentModelSelect = document.querySelector(
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

  it("leaves the sub-agent model blank so the main profile model is used", async () => {
    const user = userEvent.setup();
    vi.mocked(createModelProfile).mockResolvedValue({
      model_profile: makeConfigBootstrap().model_profiles[0],
      config_revision: "rev-2",
    });

    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Add Profile" }));
    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("openai-main"),
    );

    await user.type(
      document.querySelector<HTMLInputElement>('input[name="profile-name"]')!,
      "Opus",
    );
    await user.selectOptions(
      document.querySelector<HTMLSelectElement>('select[name="model"]')!,
      "gpt-5.4",
    );
    expect(
      await screen.findByText("Leave blank to use this profile's main model."),
    ).toBeInTheDocument();
    expect(
      document.querySelector<HTMLSelectElement>('select[name="sub-agent-model"]')
        ?.value,
    ).toBe("");

    await user.click(screen.getByRole("button", { name: "Add Profile" }));

    await waitFor(() =>
      expect(createModelProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          model: "gpt-5.4",
          sub_agent_model: null,
        }),
        "rev-1",
      ),
    );
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

    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Add Profile" }));

    await screen.findByText("Missing authentication for provider 'openai'.");
    expect(document.querySelector('input[name="model"]')).not.toBeNull();
    expect(document.querySelector('select[name="model"]')).toBeNull();
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

    renderWithProviders(<SettingsPage />);

    await screen.findByRole("button", { name: "Add Profile" });
    await user.click(screen.getAllByRole("button", { name: "Edit" })[2]);

    await waitFor(() =>
      expect(fetchProviderModels).toHaveBeenCalledWith("openai-main"),
    );

    const modelInput = document.querySelector<HTMLInputElement>(
      'input[name="model"]',
    );
    const subAgentModelInput = document.querySelector<HTMLInputElement>(
      'input[name="sub-agent-model"]',
    );
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
