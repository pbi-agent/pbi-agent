import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import { SessionPage } from "./SessionPage";
import { renderWithProviders } from "../../test/render";
import {
  ApiError,
  createLiveSession,
  expandSessionInput,
  fetchConfigBootstrap,
  fetchLiveSessionDetail,
  fetchSessionDetail,
  fetchSessions,
  interruptLiveSession,
  runShellCommand,
  submitSessionInput,
  uploadSessionImages,
} from "../../api";
import type {
  ConfigBootstrapPayload,
  ExpandedSessionInput,
  LiveSession,
  LiveSessionSnapshot,
  SessionDetailPayload,
  SessionRecord,
} from "../../types";

vi.mock("../../hooks/useLiveSessionEvents", () => ({
  useLiveSessionEvents: vi.fn(),
}));

vi.mock("./ConnectionBadge", () => ({
  ConnectionBadge: ({ connection }: { connection: string }) => <div>Connection {connection}</div>,
}));

vi.mock("./RunHistory", () => ({
  RunHistory: ({ sessionId }: { sessionId: string }) => <div>Run History {sessionId}</div>,
}));

vi.mock("./SessionSidebar", () => ({
  SessionSidebar: ({
    sessions,
    onNewSession,
  }: {
    sessions: SessionRecord[];
    onNewSession: () => void;
  }) => (
    <div>
      <div>Sidebar {sessions.length}</div>
      <button type="button" onClick={onNewSession}>New Session</button>
    </div>
  ),
}));

vi.mock("./SessionTimeline", () => ({
  SessionTimeline: ({ items }: { items: unknown[] }) => <div>Timeline {items.length}</div>,
}));

vi.mock("./UsageBar", () => ({
  UsageBar: () => <div>Usage Bar</div>,
}));

vi.mock("./DeleteSessionModal", () => ({
  DeleteSessionModal: () => <div>Delete Session Modal</div>,
}));

vi.mock("./Composer", async () => {
  const React = await import("react");

  return {
    Composer: React.forwardRef(function MockComposer(
      {
        supportsImageInputs,
        isSubmitting,
        onSubmit,
        isProcessing,
        canInterrupt,
        isInterrupting,
        onInterrupt,
        restoredInput,
      }: {
        supportsImageInputs: boolean;
        isSubmitting: boolean;
        onSubmit: (payload: { text: string; images: File[] }) => Promise<void>;
        isProcessing?: boolean;
        canInterrupt?: boolean;
        isInterrupting?: boolean;
        onInterrupt?: () => void;
        restoredInput?: string | null;
      },
      ref,
    ) {
      React.useImperativeHandle(ref, () => ({
        focus: vi.fn(),
      }));

      return (
        <div>
          <div>Composer images {String(supportsImageInputs)}</div>
          <div>Composer submitting {String(isSubmitting)}</div>
          <div>Composer restored {restoredInput ?? ""}</div>
          {isProcessing && canInterrupt ? (
            <button
              type="button"
              aria-label="Interrupt assistant turn"
              disabled={Boolean(isInterrupting)}
              onClick={() => onInterrupt?.()}
            >
              Stop
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => {
              void onSubmit({
                text: "review @docs",
                images: [new File(["image"], "diagram.png", { type: "image/png" })],
              });
            }}
          >
            Submit Expanded
          </button>
          <button
            type="button"
            onClick={() => {
              void onSubmit({
                text: "/plan",
                images: [new File(["image"], "slash-diagram.png", { type: "image/png" })],
              });
            }}
          >
            Submit Slash
          </button>
          <button
            type="button"
            onClick={() => {
              void onSubmit({ text: "!ls -la", images: [] });
            }}
          >
            Submit Shell
          </button>
        </div>
      );
    }),
  };
});

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    createLiveSession: vi.fn(),
    deleteSession: vi.fn(),
    expandSessionInput: vi.fn(),
    fetchConfigBootstrap: vi.fn(),
    fetchLiveSessionDetail: vi.fn(),
    fetchSessionDetail: vi.fn(),
    fetchSessions: vi.fn(),
    interruptLiveSession: vi.fn(),
    runShellCommand: vi.fn(),
    setActiveModelProfile: vi.fn(),
    setLiveSessionProfile: vi.fn(),
    submitSessionInput: vi.fn(),
    uploadSessionImages: vi.fn(),
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
          provider: "openai",
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
    ],
    commands: [],
    options: {
      provider_kinds: ["openai"],
      reasoning_efforts: ["high"],
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
      },
    },
    ...overrides,
  };
}

function makeLiveSession(overrides: Partial<LiveSession> = {}): LiveSession {
  return {
    live_session_id: "live-1",
    session_id: null,
    task_id: null,
    kind: "session",
    project_dir: "/workspace",
    created_at: "2026-04-16T10:00:00Z",
    status: "running",
    exit_code: null,
    fatal_error: null,
    ended_at: null,
    last_event_seq: 1,
    provider_id: "openai-main",
    profile_id: "analysis",
    provider: "openai",
    model: "gpt-5.4",
    reasoning_effort: "high",
    ...overrides,
  };
}

function makeSnapshot(
  overrides: Partial<LiveSessionSnapshot> = {},
): LiveSessionSnapshot {
  return {
    live_session_id: "live-1",
    session_id: null,
    runtime: null,
    input_enabled: true,
    wait_message: null,
    processing: null,
    session_usage: null,
    turn_usage: null,
    session_ended: false,
    fatal_error: null,
    items: [
      {
        kind: "message",
        itemId: "message-1",
        role: "assistant",
        content: "ready",
        markdown: false,
      },
    ],
    sub_agents: {},
    last_event_seq: 1,
    ...overrides,
  };
}

function makeSessionRecord(overrides: Partial<SessionRecord> = {}): SessionRecord {
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

function renderSessionRoute(route: string) {
  return renderWithProviders(
    <Routes>
      <Route
        path="/sessions"
        element={<SessionPage workspaceRoot="/workspace" supportsImageInputs />}
      />
      <Route
        path="/sessions/:sessionId"
        element={<SessionPage workspaceRoot="/workspace" supportsImageInputs />}
      />
      <Route
        path="/sessions/live/:liveSessionId"
        element={<SessionPage workspaceRoot="/workspace" supportsImageInputs />}
      />
    </Routes>,
    { route },
  );
}

describe("SessionPage", () => {
  beforeEach(() => {
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(makeConfigBootstrap());
    vi.mocked(fetchSessions).mockResolvedValue([makeSessionRecord()]);
    vi.mocked(fetchLiveSessionDetail).mockResolvedValue({
      live_session: makeLiveSession(),
      snapshot: makeSnapshot(),
    });
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord(),
      history_items: [],
      active_live_session: null,
    } satisfies SessionDetailPayload);
    vi.mocked(expandSessionInput).mockResolvedValue({
      text: "review @docs and @images/diagram.png",
      file_paths: ["docs/spec.md"],
      image_paths: ["images/diagram.png", "images/diagram.png"],
      warnings: ["Expanded one mention."],
    } satisfies ExpandedSessionInput);
    vi.mocked(uploadSessionImages).mockResolvedValue([
      {
        upload_id: "upload-1",
        name: "diagram.png",
        mime_type: "image/png",
        byte_count: 5,
        preview_url: "/api/uploads/upload-1",
      },
    ]);
    vi.mocked(runShellCommand).mockResolvedValue(makeLiveSession());
    vi.mocked(submitSessionInput).mockResolvedValue(makeLiveSession());
    vi.mocked(interruptLiveSession).mockResolvedValue(makeLiveSession());
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("expands input, shows warnings, uploads images, and submits the merged payload", async () => {
    const user = userEvent.setup();

    renderSessionRoute("/sessions/live/live-1");

    expect(await screen.findByText("Timeline 1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit Expanded" }));

    await waitFor(() => expect(submitSessionInput).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Expanded one mention.")).toBeInTheDocument();
    expect(uploadSessionImages).toHaveBeenCalledWith(
      "live-1",
      expect.arrayContaining([expect.any(File)]),
    );
    expect(submitSessionInput).toHaveBeenCalledWith("live-1", {
      text: "review @docs and @images/diagram.png",
      file_paths: ["docs/spec.md"],
      image_paths: ["images/diagram.png"],
      image_upload_ids: ["upload-1"],
      profile_id: "analysis",
    });
  });

  it("shows interrupt only while processing and calls interrupt endpoint", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchLiveSessionDetail).mockResolvedValue({
      live_session: makeLiveSession(),
      snapshot: makeSnapshot({
        input_enabled: false,
        processing: {
          active: true,
          phase: "model_wait",
          message: "Working...",
        },
      }),
    });

    renderSessionRoute("/sessions/live/live-1");

    const button = await screen.findByRole("button", {
      name: "Interrupt assistant turn",
    });
    await user.click(button);

    await waitFor(() => expect(interruptLiveSession).toHaveBeenCalledWith("live-1"));
  });

  it("hides interrupt while idle", async () => {
    renderSessionRoute("/sessions/live/live-1");

    expect(await screen.findByText("Timeline 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Interrupt assistant turn" })).toBeNull();
  });

  it("sends slash commands directly with image uploads and without expansion", async () => {
    const user = userEvent.setup();

    renderSessionRoute("/sessions/live/live-1");

    expect(await screen.findByText("Timeline 1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit Slash" }));

    await waitFor(() => expect(submitSessionInput).toHaveBeenCalledTimes(1));
    expect(expandSessionInput).not.toHaveBeenCalled();
    expect(uploadSessionImages).toHaveBeenCalledWith(
      "live-1",
      expect.arrayContaining([expect.any(File)]),
    );
    expect(submitSessionInput).toHaveBeenCalledWith("live-1", {
      text: "/plan",
      file_paths: [],
      image_paths: [],
      image_upload_ids: ["upload-1"],
      profile_id: "analysis",
    });
  });

  it("runs bang-prefixed shell commands without expansion, uploads, or model input", async () => {
    const user = userEvent.setup();

    renderSessionRoute("/sessions/live/live-1");

    expect(await screen.findByText("Timeline 1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit Shell" }));

    await waitFor(() => expect(runShellCommand).toHaveBeenCalledTimes(1));
    expect(expandSessionInput).not.toHaveBeenCalled();
    expect(uploadSessionImages).not.toHaveBeenCalled();
    expect(submitSessionInput).not.toHaveBeenCalled();
    expect(runShellCommand).toHaveBeenCalledWith("live-1", { command: "ls -la" });
  });

  it("marks the composer as submitting while shell commands are pending", async () => {
    const user = userEvent.setup();
    vi.mocked(runShellCommand).mockReturnValue(new Promise(() => undefined));

    renderSessionRoute("/sessions/live/live-1");

    expect(await screen.findByText("Timeline 1")).toBeInTheDocument();
    expect(screen.getByText("Composer submitting false")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit Shell" }));

    await waitFor(() => expect(runShellCommand).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Composer submitting true")).toBeInTheDocument();
  });

  it("renders the not-found state for missing saved sessions", async () => {
    vi.mocked(fetchSessionDetail).mockRejectedValue(
      new ApiError("Session missing from this workspace.", 404),
    );

    renderSessionRoute("/sessions/missing-session");

    expect(await screen.findByText("Session not found")).toBeInTheDocument();
    expect(screen.getByText("Session missing from this workspace.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start new session" })).toBeInTheDocument();
  });

  it("reopens saved sessions with the explicit resume_session_id payload", async () => {
    vi.mocked(createLiveSession).mockResolvedValue(
      makeLiveSession({ session_id: "session-1" }),
    );

    renderSessionRoute("/sessions/session-1");

    await waitFor(() => {
      expect(createLiveSession).toHaveBeenCalled();
      expect(vi.mocked(createLiveSession).mock.calls[0]?.[0]).toEqual({
        resume_session_id: "session-1",
      });
    });
  });
});
