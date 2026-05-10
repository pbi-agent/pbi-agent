import userEvent from "@testing-library/user-event";
import { act, screen, waitFor, within } from "@testing-library/react";
import { SettingsPage } from "./SettingsPage";
import { ThemeProvider } from "../ThemeProvider";
import { renderWithProviders } from "../../test/render";
import { useSettingsDialog } from "../../hooks/useSettingsDialog";
import {
  ApiError,
  createProvider,
  createModelProfile,
  fetchAgentCandidates,
  fetchCommandCandidates,
  fetchConfigBootstrap,
  fetchProviderModels,
  fetchProviderAuthFlow,
  fetchProviderUsageLimits,
  fetchSkillCandidates,
  installAgent,
  installCommand,
  installSkill,
  logoutProviderAuth,
  refreshProviderAuth,
  setActiveModelProfile,
  startProviderAuthFlow,
  updateMaintenanceConfig,
} from "../../api";
import type { ConfigBootstrapPayload } from "../../types";
import {
  readNotificationPreferences,
  resetNotificationPreferencesForTests,
  setNotificationPreferences,
} from "../../lib/notificationPreferences";

const originalNotification = globalThis.Notification;
const originalAudioContext = window.AudioContext;

function installNotificationMock(permission: NotificationPermission) {
  class NotificationMock {
    static permission: NotificationPermission = "default";
    static requestPermission = vi.fn().mockResolvedValue(permission);
  }

  Object.defineProperty(globalThis, "Notification", {
    configurable: true,
    writable: true,
    value: NotificationMock,
  });
  return NotificationMock;
}

function restoreNotificationMock() {
  if (originalNotification) {
    Object.defineProperty(globalThis, "Notification", {
      configurable: true,
      writable: true,
      value: originalNotification,
    });
  } else {
    Reflect.deleteProperty(globalThis, "Notification");
  }

  Object.defineProperty(window, "AudioContext", {
    configurable: true,
    writable: true,
    value: originalAudioContext,
  });
}

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
    fetchProviderUsageLimits: vi.fn(),
    fetchAgentCandidates: vi.fn(),
    installAgent: vi.fn(),
    fetchCommandCandidates: vi.fn(),
    installCommand: vi.fn(),
    fetchSkillCandidates: vi.fn(),
    installSkill: vi.fn(),
    refreshProviderAuth: vi.fn(),
    logoutProviderAuth: vi.fn(),
    updateMaintenanceConfig: vi.fn(),
  };
});

function makeConfigBootstrap(
  overrides: Partial<ConfigBootstrapPayload> = {},
): ConfigBootstrapPayload {
  return {
    config_revision: "rev-1",
    active_profile_id: "analysis",
    maintenance: { retention_days: 30 },
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
        compact_tail_turns: 2,
        compact_preserve_recent_tokens: 8000,
        compact_tool_output_max_chars: 2000,
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
      compact_tail_turns: 2,
      compact_preserve_recent_tokens: 8000,
      compact_tool_output_max_chars: 2000,
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
        compact_tail_turns: 2,
        compact_preserve_recent_tokens: 8000,
        compact_tool_output_max_chars: 2000,
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
      compact_tail_turns: 2,
      compact_preserve_recent_tokens: 8000,
      compact_tool_output_max_chars: 2000,
          responses_url: "https://api.openai.com/v1/responses",
          generic_api_url: "https://api.openai.com/v1/chat/completions",
          supports_image_inputs: true,
        },
      },
    ],
    commands: [],
    skills: [],
    agents: [],
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

async function openSettingsTab(
  user: ReturnType<typeof userEvent.setup>,
  tabName: string,
) {
  const label = await screen.findByText(tabName, {
    selector: ".settings-nav__item-label",
  });
  const button = label.closest("button");
  expect(button).not.toBeNull();
  await user.click(button!);
}

describe("SettingsPage", () => {
  beforeEach(() => {
    act(() => {
      useSettingsDialog.getState().openSettings();
    });
    resetNotificationPreferencesForTests();
    window.localStorage.removeItem("pbi-agent-theme");
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.classList.remove("dark");
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
    vi.mocked(fetchProviderUsageLimits).mockResolvedValue({
      provider_id: "chatgpt-main",
      provider_kind: "chatgpt",
      account_label: "user@example.com",
      plan_type: "Plus",
      fetched_at: "2026-05-01T00:00:00Z",
      buckets: [],
    });
    vi.mocked(fetchCommandCandidates).mockResolvedValue({
      source: "https://github.com/pbi-agent/commands",
      ref: null,
      candidates: [
        {
          name: "Repo Review",
          command_id: "repo-review",
          slash_alias: "/repo-review",
          description: "Review repository changes",
          model_profile_id: null,
          subpath: null,
        },
      ],
    });
    vi.mocked(installCommand).mockResolvedValue({
      installed: {
        command_id: "repo-review",
        slash_alias: "/repo-review",
        install_path: ".agents/commands/repo-review.md",
        source: "https://github.com/pbi-agent/commands",
        ref: null,
        subpath: null,
      },
      commands: [
        {
          id: "repo-review",
          name: "Repo Review",
          slash_alias: "/repo-review",
          description: "Review repository changes",
          instructions: "# Repo Review\n\nReview repository changes.",
          path: ".agents/commands/repo-review.md",
          model_profile_id: null,
        },
      ],
      config_revision: "rev-2",
    });
    vi.mocked(fetchSkillCandidates).mockResolvedValue({
      source: "https://github.com/pbi-agent/skills",
      ref: null,
      candidates: [
        {
          name: "repo-review",
          description: "Review repository changes",
          subpath: null,
        },
      ],
    });
    vi.mocked(installSkill).mockResolvedValue({
      installed: {
        name: "repo-review",
        install_path: ".agents/skills/repo-review",
        source: "https://github.com/pbi-agent/skills",
        ref: null,
        subpath: null,
      },
      skills: [
        {
          id: "repo-review",
          name: "repo-review",
          description: "Review repository changes",
          instructions: "# repo-review\n\nReview repository changes.",
          path: ".agents/skills/repo-review/SKILL.md",
        },
      ],
      config_revision: "rev-2",
    });
    vi.mocked(fetchAgentCandidates).mockResolvedValue({
      source: "https://github.com/pbi-agent/agents",
      ref: null,
      candidates: [
        {
          agent_name: "repo-reviewer",
          description: "Review repository changes",
          model_profile_id: null,
          subpath: null,
        },
      ],
    });
    vi.mocked(installAgent).mockResolvedValue({
      installed: {
        agent_name: "repo-reviewer",
        install_path: ".agents/agents/repo-reviewer.md",
        source: "https://github.com/pbi-agent/agents",
        ref: null,
        subpath: null,
      },
      agents: [
        {
          id: "repo-reviewer",
          name: "repo-reviewer",
          description: "Review repository changes",
          instructions: "Review repository changes.",
          path: ".agents/agents/repo-reviewer.md",
          model_profile_id: null,
        },
      ],
      config_revision: "rev-2",
    });
    vi.mocked(updateMaintenanceConfig).mockResolvedValue({
      maintenance: { retention_days: 14 },
      config_revision: "rev-2",
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
    act(() => {
      useSettingsDialog.getState().closeSettings();
    });
    restoreNotificationMock();
    window.localStorage.removeItem("pbi-agent-theme");
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.classList.remove("dark");
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("renders notification controls with desktop and sound disabled by default", async () => {
    renderWithProviders(<SettingsPage />);

    const desktopCheckbox = await screen.findByRole("checkbox", {
      name: /desktop notifications/i,
    });
    const soundCheckbox = screen.getByRole("checkbox", {
      name: /sound notifications/i,
    });

    expect(desktopCheckbox).not.toBeChecked();
    expect(soundCheckbox).not.toBeChecked();
    expect(screen.getByText(/session\s+finishes/i)).toBeInTheDocument();
  });

  it("renders theme choices in the appearance tab", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Appearance");

    expect(screen.getByRole("radio", { name: "Prism theme" })).toHaveAttribute(
      "data-theme-option",
      "prism",
    );
    expect(screen.getByRole("radio", { name: "Light theme" })).toHaveAttribute(
      "data-theme-option",
      "light",
    );
    expect(screen.getByRole("radio", { name: "Dark theme" })).toHaveAttribute(
      "data-theme-option",
      "dark",
    );
  });

  it("changes and persists the selected theme from the appearance tab", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <ThemeProvider>
        <SettingsPage />
      </ThemeProvider>,
    );

    await openSettingsTab(user, "Appearance");
    const lightThemeOption = screen.getByRole("radio", { name: "Light theme" });

    await user.click(lightThemeOption);

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
    expect(window.localStorage.getItem("pbi-agent-theme")).toBe("light");
    expect(lightThemeOption).toHaveAttribute("data-state", "on");
    expect(lightThemeOption).toHaveAttribute("aria-checked", "true");
  });

  it("requests browser permission from the desktop notification control", async () => {
    const user = userEvent.setup();
    const notificationMock = installNotificationMock("granted");

    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("checkbox", {
      name: /desktop notifications/i,
    }));

    await waitFor(() =>
      expect(notificationMock.requestPermission).toHaveBeenCalledTimes(1),
    );
    expect(readNotificationPreferences().desktopEnabled).toBe(true);
  });

  it("keeps desktop notifications disabled when browser permission is denied", async () => {
    const user = userEvent.setup();
    installNotificationMock("denied");

    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("checkbox", {
      name: /desktop notifications/i,
    }));

    await waitFor(() =>
      expect(readNotificationPreferences().desktopEnabled).toBe(false),
    );
  });

  it("persists the sound notification setting and reveals the sound picker", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    expect(
      screen.queryByRole("combobox", { name: /notification sound/i }),
    ).not.toBeInTheDocument();

    await user.click(await screen.findByRole("checkbox", {
      name: /sound notifications/i,
    }));

    expect(readNotificationPreferences().soundEnabled).toBe(true);
    expect(
      screen.getByRole("combobox", { name: /notification sound/i }),
    ).toBeInTheDocument();
  });

  it("persists the selected notification sound", async () => {
    const user = userEvent.setup();
    setNotificationPreferences({ soundEnabled: true });

    renderWithProviders(<SettingsPage />);

    await user.selectOptions(
      await screen.findByRole("combobox", { name: /notification sound/i }),
      "pulse",
    );

    expect(readNotificationPreferences().soundId).toBe("pulse");
    expect(screen.getByText(/two quick alert pulses/i)).toBeInTheDocument();
  });

  it("hides notification sound selection and preview when sounds are disabled", async () => {
    renderWithProviders(<SettingsPage />);

    await screen.findByRole("checkbox", { name: /sound notifications/i });

    expect(
      screen.queryByRole("combobox", { name: /notification sound/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /preview notification sound/i }),
    ).not.toBeInTheDocument();
  });

  it("previews the selected notification sound when sounds are enabled", async () => {
    const user = userEvent.setup();
    const start = vi.fn();
    const stop = vi.fn();
    const connect = vi.fn();
    const setValueAtTime = vi.fn();
    const exponentialRampToValueAtTime = vi.fn();
    setNotificationPreferences({ soundEnabled: true, soundId: "pop" });

    class AudioContextMock {
      state = "running" as AudioContextState;
      currentTime = 1;
      destination = {} as AudioDestinationNode;
      close = vi.fn();
      resume = vi.fn();

      createOscillator() {
        return {
          type: "sine" as OscillatorType,
          frequency: { setValueAtTime, exponentialRampToValueAtTime },
          connect,
          start,
          stop,
          addEventListener: vi.fn((_event: string, callback: () => void) => callback()),
        };
      }

      createGain() {
        return {
          gain: { setValueAtTime, exponentialRampToValueAtTime },
          connect,
        };
      }
    }

    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      writable: true,
      value: AudioContextMock,
    });

    renderWithProviders(<SettingsPage />);

    await user.click(
      await screen.findByRole("button", { name: /preview notification sound/i }),
    );

    expect(start).toHaveBeenCalled();
    expect(stop).toHaveBeenCalledTimes(start.mock.calls.length);
  });

  it("shows command cards with skill-style metadata and previews markdown", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        commands: [
          {
            id: "review",
            name: "Review",
            slash_alias: "/review",
            description: "Review Mode",
            path: ".agents/commands/review.md",
            model_profile_id: "analysis",
            instructions:
              "# Review Mode\n\nReview proposed code changes.\n\n- Bugs\n- Tests",
          },
        ],
      }),
    );

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Commands");

    expect(await screen.findByText("Review")).toBeInTheDocument();
    expect(screen.getAllByText(/\/review/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Review Mode")).toBeInTheDocument();
    expect(screen.getByText("Profile: analysis")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Preview" }));

    const dialog = await screen.findByRole("dialog", { name: "Review" });
    expect(within(dialog).getByRole("heading", { name: "Review Mode" })).toBeInTheDocument();
    expect(within(dialog).getByText("Review proposed code changes.")).toBeInTheDocument();
    expect(within(dialog).getByText("Bugs")).toBeInTheDocument();
  });

  it("does not fetch command candidates until the add command dialog opens", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Commands");

    expect(await screen.findByText("Project Commands")).toBeInTheDocument();
    expect(fetchCommandCandidates).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Add Command" }));

    await waitFor(() => expect(fetchCommandCandidates).toHaveBeenCalledWith(null));
  });

  it("loads default command candidates when opening Add Command", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Commands");
    await user.click(await screen.findByRole("button", { name: "Add Command" }));

    const dialog = await screen.findByRole("dialog", {
      name: "Add Project Command",
    });
    expect(await within(dialog).findByText("/repo-review")).toBeInTheDocument();
    expect(fetchCommandCandidates).toHaveBeenCalledWith(null);
  });

  it("installs a selected command, refetches settings, and shows success", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap)
      .mockResolvedValueOnce(makeConfigBootstrap())
      .mockResolvedValue(
        makeConfigBootstrap({
          config_revision: "rev-2",
          commands: [
            {
              id: "repo-review",
              name: "Repo Review",
              slash_alias: "/repo-review",
              description: "Review repository changes",
              instructions: "# Repo Review\n\nReview repository changes.",
              path: ".agents/commands/repo-review.md",
              model_profile_id: null,
            },
          ],
        }),
      );

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Commands");
    await user.click(await screen.findByRole("button", { name: "Add Command" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Add Project Command",
    });
    await within(dialog).findByText("/repo-review");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));

    await waitFor(() =>
      expect(installCommand).toHaveBeenCalledWith({
        source: "https://github.com/pbi-agent/commands",
        command_name: "repo-review",
      }),
    );
    await waitFor(() => expect(fetchConfigBootstrap).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Installed \/repo-review/i)).toBeInTheDocument();
    expect(
      await screen.findByText(".agents/commands/repo-review.md"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("dialog", { name: "Add Project Command" }),
    ).not.toBeInTheDocument();
  });

  it("reveals Replace existing on command install conflict and retries with force", async () => {
    const user = userEvent.setup();
    vi.mocked(installCommand)
      .mockRejectedValueOnce(new ApiError("Command already installed", 409))
      .mockResolvedValueOnce({
        installed: {
          command_id: "repo-review",
          slash_alias: "/repo-review",
          install_path: ".agents/commands/repo-review.md",
          source: "https://github.com/pbi-agent/commands",
          ref: null,
          subpath: null,
        },
        commands: [
          {
            id: "repo-review",
            name: "Repo Review",
            slash_alias: "/repo-review",
            description: "Review repository changes",
            instructions: "# Repo Review\n\nReview repository changes.",
            path: ".agents/commands/repo-review.md",
            model_profile_id: null,
          },
        ],
        config_revision: "rev-2",
      });

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Commands");
    await user.click(await screen.findByRole("button", { name: "Add Command" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Add Project Command",
    });
    await within(dialog).findByText("/repo-review");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));

    expect(await within(dialog).findByText("Command already installed")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Replace existing" }));

    await waitFor(() =>
      expect(installCommand).toHaveBeenLastCalledWith({
        source: "https://github.com/pbi-agent/commands",
        command_name: "repo-review",
        force: true,
      }),
    );
  });

  it("browses command candidates from a custom source", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchCommandCandidates)
      .mockResolvedValueOnce({
        source: "https://github.com/pbi-agent/commands",
        ref: null,
        candidates: [],
      })
      .mockResolvedValueOnce({
        source: "owner/private-repo",
        ref: "main",
        candidates: [
          {
            name: "Private Review",
            command_id: "private-review",
            slash_alias: "/private-review",
            description: "Private review workflow",
            model_profile_id: "analysis",
            subpath: "commands/private-review.md",
          },
        ],
      });

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Commands");
    await user.click(await screen.findByRole("button", { name: "Add Command" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Add Project Command",
    });
    await waitFor(() => expect(fetchCommandCandidates).toHaveBeenCalledWith(null));

    await user.type(
      within(dialog).getByLabelText("Custom source"),
      "owner/private-repo",
    );
    await user.click(within(dialog).getByRole("button", { name: "Browse" }));

    await waitFor(() =>
      expect(fetchCommandCandidates).toHaveBeenLastCalledWith("owner/private-repo"),
    );
    expect(await within(dialog).findByText("/private-review")).toBeInTheDocument();
    expect(within(dialog).getByText("Profile: analysis")).toBeInTheDocument();
  });

  it("shows Project navigation with Skills, Commands, and Agents", async () => {
    renderWithProviders(<SettingsPage />);

    expect(
      await screen.findByText("Project", {
        selector: ".settings-nav__group-label",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Skills", { selector: ".settings-nav__item-label" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Commands", { selector: ".settings-nav__item-label" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Agents", { selector: ".settings-nav__item-label" }),
    ).toBeInTheDocument();
  });

  it("shows agent cards with preview markdown", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        agents: [
          {
            id: "code-reviewer",
            name: "code-reviewer",
            description: "Review code changes",
            instructions: "# Agent Prompt\n\nReview code changes carefully.",
            path: ".agents/agents/code-reviewer.md",
            model_profile_id: "analysis",
          },
        ],
      }),
    );

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Agents");

    expect(await screen.findByText("code-reviewer")).toBeInTheDocument();
    expect(screen.getByText("Review code changes")).toBeInTheDocument();
    expect(screen.getByText("Profile: analysis")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Preview" }));

    const dialog = await screen.findByRole("dialog", { name: "code-reviewer" });
    expect(within(dialog).getByRole("heading", { name: "Agent Prompt" })).toBeInTheDocument();
    expect(within(dialog).getByText("Review code changes carefully.")).toBeInTheDocument();
  });

  it("does not fetch agent candidates until the add agent dialog opens", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Agents");

    expect(await screen.findByText("Project Agents")).toBeInTheDocument();
    expect(fetchAgentCandidates).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Add Agent" }));

    await waitFor(() => expect(fetchAgentCandidates).toHaveBeenCalledWith(null));
  });

  it("loads default agent candidates when opening Add Agent", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Agents");
    await user.click(await screen.findByRole("button", { name: "Add Agent" }));

    const dialog = await screen.findByRole("dialog", { name: "Add Project Agent" });
    expect(await within(dialog).findByText("repo-reviewer")).toBeInTheDocument();
    expect(fetchAgentCandidates).toHaveBeenCalledWith(null);
  });

  it("installs a selected agent, refetches settings, and shows success", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap)
      .mockResolvedValueOnce(makeConfigBootstrap())
      .mockResolvedValue(
        makeConfigBootstrap({
          config_revision: "rev-2",
          agents: [
            {
              id: "repo-reviewer",
              name: "repo-reviewer",
              description: "Review repository changes",
              instructions: "Review repository changes.",
              path: ".agents/agents/repo-reviewer.md",
              model_profile_id: null,
            },
          ],
        }),
      );

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Agents");
    await user.click(await screen.findByRole("button", { name: "Add Agent" }));
    const dialog = await screen.findByRole("dialog", { name: "Add Project Agent" });
    await within(dialog).findByText("repo-reviewer");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));

    await waitFor(() =>
      expect(installAgent).toHaveBeenCalledWith({
        source: "https://github.com/pbi-agent/agents",
        agent_name: "repo-reviewer",
      }),
    );
    await waitFor(() => expect(fetchConfigBootstrap).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Installed repo-reviewer/i)).toBeInTheDocument();
    expect(
      await screen.findByText(".agents/agents/repo-reviewer.md"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Add Project Agent" })).not.toBeInTheDocument();
  });

  it("reveals Replace existing on agent install conflict and retries with force", async () => {
    const user = userEvent.setup();
    vi.mocked(installAgent)
      .mockRejectedValueOnce(new ApiError("Agent already installed", 409))
      .mockResolvedValueOnce({
        installed: {
          agent_name: "repo-reviewer",
          install_path: ".agents/agents/repo-reviewer.md",
          source: "https://github.com/pbi-agent/agents",
          ref: null,
          subpath: null,
        },
        agents: [
          {
            id: "repo-reviewer",
            name: "repo-reviewer",
            description: "Review repository changes",
            instructions: "Review repository changes.",
            path: ".agents/agents/repo-reviewer.md",
            model_profile_id: null,
          },
        ],
        config_revision: "rev-2",
      });

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Agents");
    await user.click(await screen.findByRole("button", { name: "Add Agent" }));
    const dialog = await screen.findByRole("dialog", { name: "Add Project Agent" });
    await within(dialog).findByText("repo-reviewer");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));

    expect(await within(dialog).findByText("Agent already installed")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Replace existing" }));

    await waitFor(() =>
      expect(installAgent).toHaveBeenLastCalledWith({
        source: "https://github.com/pbi-agent/agents",
        agent_name: "repo-reviewer",
        force: true,
      }),
    );
  });

  it("browses agent candidates from a custom source", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAgentCandidates)
      .mockResolvedValueOnce({
        source: "https://github.com/pbi-agent/agents",
        ref: null,
        candidates: [],
      })
      .mockResolvedValueOnce({
        source: "owner/private-repo",
        ref: "main",
        candidates: [
          {
            agent_name: "private-reviewer",
            description: "Private reviewer",
            model_profile_id: null,
            subpath: "agents/private-reviewer.md",
          },
        ],
      });

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Agents");
    await user.click(await screen.findByRole("button", { name: "Add Agent" }));
    const dialog = await screen.findByRole("dialog", { name: "Add Project Agent" });
    await waitFor(() => expect(fetchAgentCandidates).toHaveBeenCalledWith(null));

    await user.type(
      within(dialog).getByLabelText("Custom source"),
      "owner/private-repo",
    );
    await user.click(within(dialog).getByRole("button", { name: "Browse" }));

    await waitFor(() =>
      expect(fetchAgentCandidates).toHaveBeenLastCalledWith("owner/private-repo"),
    );
    expect(await within(dialog).findByText("private-reviewer")).toBeInTheDocument();
  });

  it("shows skill cards with preview markdown", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        skills: [
          {
            id: "focus",
            name: "focus",
            description: "Keep implementation focused",
            instructions: "# Focus Skill\n\nKeep implementation focused.\n\n- Scope\n- Verify",
            path: ".agents/skills/focus/SKILL.md",
          },
        ],
      }),
    );

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Skills");

    expect(await screen.findByText("focus")).toBeInTheDocument();
    expect(screen.getByText("Keep implementation focused")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Preview" }));

    const dialog = await screen.findByRole("dialog", { name: "focus" });
    expect(within(dialog).getByRole("heading", { name: "Focus Skill" })).toBeInTheDocument();
    expect(within(dialog).getByText("Keep implementation focused.")).toBeInTheDocument();
    expect(within(dialog).getByText("Scope")).toBeInTheDocument();
  });

  it("does not fetch skill candidates until the add skill dialog opens", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Skills");

    expect(await screen.findByText("Project Skills")).toBeInTheDocument();
    expect(fetchSkillCandidates).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Add Skill" }));

    await waitFor(() => expect(fetchSkillCandidates).toHaveBeenCalledWith(null));
  });

  it("loads default skill candidates when opening Add Skill", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Skills");
    await user.click(await screen.findByRole("button", { name: "Add Skill" }));

    const dialog = await screen.findByRole("dialog", { name: "Add Project Skill" });
    expect(await within(dialog).findByText("repo-review")).toBeInTheDocument();
    expect(fetchSkillCandidates).toHaveBeenCalledWith(null);
  });

  it("installs a selected skill, refetches settings, and shows success", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap)
      .mockResolvedValueOnce(makeConfigBootstrap())
      .mockResolvedValue(
        makeConfigBootstrap({
          config_revision: "rev-2",
          skills: [
            {
              id: "repo-review",
              name: "repo-review",
              description: "Review repository changes",
              instructions: "# repo-review\n\nReview repository changes.",
              path: ".agents/skills/repo-review/SKILL.md",
            },
          ],
        }),
      );

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Skills");
    await user.click(await screen.findByRole("button", { name: "Add Skill" }));
    const dialog = await screen.findByRole("dialog", { name: "Add Project Skill" });
    await within(dialog).findByText("repo-review");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));

    await waitFor(() =>
      expect(installSkill).toHaveBeenCalledWith({
        source: "https://github.com/pbi-agent/skills",
        skill_name: "repo-review",
      }),
    );
    await waitFor(() => expect(fetchConfigBootstrap).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Installed repo-review/i)).toBeInTheDocument();
    expect(
      await screen.findByText(".agents/skills/repo-review/SKILL.md"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Add Project Skill" })).not.toBeInTheDocument();
  });

  it("reveals Replace existing on skill install conflict and retries with force", async () => {
    const user = userEvent.setup();
    vi.mocked(installSkill)
      .mockRejectedValueOnce(new ApiError("Skill already installed", 409))
      .mockResolvedValueOnce({
        installed: {
          name: "repo-review",
          install_path: ".agents/skills/repo-review",
          source: "https://github.com/pbi-agent/skills",
          ref: null,
          subpath: null,
        },
        skills: [
          {
            id: "repo-review",
            name: "repo-review",
            description: "Review repository changes",
            instructions: "# repo-review\n\nReview repository changes.",
            path: ".agents/skills/repo-review/SKILL.md",
          },
        ],
        config_revision: "rev-2",
      });

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Skills");
    await user.click(await screen.findByRole("button", { name: "Add Skill" }));
    const dialog = await screen.findByRole("dialog", { name: "Add Project Skill" });
    await within(dialog).findByText("repo-review");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));

    expect(await within(dialog).findByText("Skill already installed")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Replace existing" }));

    await waitFor(() =>
      expect(installSkill).toHaveBeenLastCalledWith({
        source: "https://github.com/pbi-agent/skills",
        skill_name: "repo-review",
        force: true,
      }),
    );
  });

  it("browses skill candidates from a custom source", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchSkillCandidates)
      .mockResolvedValueOnce({
        source: "https://github.com/pbi-agent/skills",
        ref: null,
        candidates: [],
      })
      .mockResolvedValueOnce({
        source: "owner/private-repo",
        ref: "main",
        candidates: [
          {
            name: "private-skill",
            description: "Private workflow",
            subpath: "skills/private-skill",
          },
        ],
      });

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Skills");
    await user.click(await screen.findByRole("button", { name: "Add Skill" }));
    const dialog = await screen.findByRole("dialog", { name: "Add Project Skill" });
    await waitFor(() => expect(fetchSkillCandidates).toHaveBeenCalledWith(null));

    await user.type(
      within(dialog).getByLabelText("Custom source"),
      "owner/private-repo",
    );
    await user.click(within(dialog).getByRole("button", { name: "Browse" }));

    await waitFor(() =>
      expect(fetchSkillCandidates).toHaveBeenLastCalledWith("owner/private-repo"),
    );
    expect(await within(dialog).findByText("private-skill")).toBeInTheDocument();
  });

  it("saves maintenance retention days", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Maintenance");

    const input = await screen.findByLabelText("Retention days");
    expect(input).toHaveValue(30);
    await user.clear(input);
    await user.type(input, "14");
    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => {
      expect(updateMaintenanceConfig).toHaveBeenCalledWith(14, "rev-1");
    });
  });

  it("rejects fractional maintenance retention days", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Maintenance");

    const input = await screen.findByLabelText("Retention days");
    await user.clear(input);
    await user.type(input, "1.5");
    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(await screen.findByText("Retention days must be a whole number of at least 1.")).toBeInTheDocument();
    expect(updateMaintenanceConfig).not.toHaveBeenCalled();
  });

  it("renders the onboarding and empty-provider states when config is blank", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        providers: [],
        model_profiles: [],
        active_profile_id: null,
      }),
    );

    renderWithProviders(<SettingsPage />);

    expect(await screen.findByText(/First-time setup:/)).toBeInTheDocument();
    await openSettingsTab(user, "Providers");
    expect(screen.getByText("No providers configured")).toBeInTheDocument();
    await openSettingsTab(user, "Model Profiles");
    expect(screen.getByRole("button", { name: "Add Profile" })).toBeDisabled();
  });

  it("updates the active default profile through the API", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Model Profiles");
    await screen.findByRole("button", { name: "Add Profile" });
    await user.selectOptions(
      document.querySelector<HTMLSelectElement>('select[name="active-profile"]')!,
      "qa",
    );

    await waitFor(() =>
      expect(setActiveModelProfile).toHaveBeenCalledWith("qa", "rev-1"),
    );
  });

  it("opens the usage-limits dialog only for connected subscription providers", async () => {
    const user = userEvent.setup();
    const base = makeConfigBootstrap();
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(
      makeConfigBootstrap({
        providers: [
          base.providers[0],
          {
            ...base.providers[1],
            auth_status: {
              ...base.providers[1].auth_status,
              session_status: "connected",
              has_session: true,
              email: "user@example.com",
              plan_type: "Plus",
            },
          },
        ],
      }),
    );
    vi.mocked(fetchProviderUsageLimits).mockResolvedValue({
      provider_id: "chatgpt-main",
      provider_kind: "chatgpt",
      account_label: "user@example.com",
      plan_type: "Plus",
      fetched_at: "2026-05-01T00:00:00Z",
      buckets: [
        {
          id: "codex",
          label: "Codex",
          unlimited: false,
          overage_allowed: false,
          overage_count: 0,
          status: "warning",
          credits: { has_credits: true, unlimited: false, balance: "9.99" },
          windows: [
            {
              name: "5h",
              used_percent: 80,
              remaining_percent: 20,
              window_minutes: 300,
              resets_at: 1_800_000_000,
              reset_at_iso: null,
              used_requests: null,
              total_requests: null,
              remaining_requests: null,
            },
            {
              name: "weekly",
              used_percent: 35,
              remaining_percent: 65,
              window_minutes: 10_080,
              resets_at: 1_800_500_000,
              reset_at_iso: null,
              used_requests: null,
              total_requests: null,
              remaining_requests: null,
            },
          ],
        },
      ],
    });

    renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Providers");
    expect(await screen.findByText("ChatGPT Main")).toBeInTheDocument();

    // Usage data must NOT be fetched eagerly on render.
    expect(fetchProviderUsageLimits).not.toHaveBeenCalled();

    // API-key providers should not expose a Usage button.
    const usageButtons = screen.getAllByRole("button", { name: "Usage" });
    expect(usageButtons).toHaveLength(1);

    await user.click(usageButtons[0]);

    expect(
      await screen.findByRole("dialog", { name: /Usage & limits/i }),
    ).toBeInTheDocument();

    expect(fetchProviderUsageLimits).toHaveBeenCalledWith("chatgpt-main");
    expect(fetchProviderUsageLimits).not.toHaveBeenCalledWith("openai-main");

    expect(await screen.findByText("Codex")).toBeInTheDocument();
    expect(screen.getByText("5h limit")).toBeInTheDocument();
    expect(screen.getByText("weekly limit")).toBeInTheDocument();
    expect(screen.getByText(/Used 80%/)).toBeInTheDocument();
    expect(screen.getByText(/Used 35%/)).toBeInTheDocument();
    expect(screen.getByText("Credits: 9.99")).toBeInTheDocument();
  });

  it("shows provider auth controls and starts the browser auth flow", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderWithProviders(<SettingsPage />);

    await openSettingsTab(user, "Providers");
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

    await openSettingsTab(user, "Providers");
    expect(await screen.findByText("Copilot Main")).toBeInTheDocument();
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

    await openSettingsTab(user, "Providers");
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

    await openSettingsTab(user, "Providers");
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

    await openSettingsTab(user, "Providers");
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

    await openSettingsTab(user, "Providers");
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

    await openSettingsTab(user, "Providers");
    expect(await screen.findByText("ChatGPT Main")).toBeInTheDocument();
    expect(screen.getByText(/not connected/)).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Connect" })[0]);
    await user.click(screen.getByRole("button", { name: "Start browser sign-in" }));
    await user.click(screen.getByRole("button", { name: "Check status" }));

    expect(await screen.findByText(/Connected as user@example.com/)).toBeInTheDocument();
    expect((await screen.findAllByText(/user@example\.com/)).length).toBeGreaterThanOrEqual(1);
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

    await openSettingsTab(user, "Providers");
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

    await openSettingsTab(user, "Providers");
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

    await openSettingsTab(user, "Model Profiles");
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

    await openSettingsTab(user, "Model Profiles");
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

    await openSettingsTab(user, "Model Profiles");
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

    await openSettingsTab(user, "Model Profiles");
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

    await openSettingsTab(user, "Model Profiles");
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

    await openSettingsTab(user, "Model Profiles");
    await screen.findByRole("button", { name: "Add Profile" });
    await user.click(screen.getByRole("button", { name: "Edit" }));

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

    await openSettingsTab(user, "Model Profiles");
    await screen.findByRole("button", { name: "Add Profile" });
    await user.selectOptions(
      document.querySelector<HTMLSelectElement>('select[name="active-profile"]')!,
      "qa",
    );

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
