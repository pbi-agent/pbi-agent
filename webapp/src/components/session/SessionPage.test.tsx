import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import { SessionPage } from "./SessionPage";
import { renderWithProviders } from "../../test/render";
import { useLiveSessionEvents } from "../../hooks/useLiveSessionEvents";
import {
  ApiError,
  expandSessionInput,
  fetchConfigBootstrap,
  fetchSessionDetail,
  fetchSessions,
  sendSessionMessage,
  updateSession,
  uploadSavedSessionImages,
} from "../../api";
import { getSavedSessionKey, useSessionStore } from "../../store";
import type {
  ConfigBootstrapPayload,
  ExpandedSessionInput,
  LiveSession,
  SessionDetailPayload,
  SessionRecord,
} from "../../types";

const usageBarMock = vi.hoisted(() => vi.fn());
const composerFocusMock = vi.hoisted(() => vi.fn());

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
    onUpdateSession,
  }: {
    sessions: SessionRecord[];
    onNewSession: () => void;
    onUpdateSession: (session: SessionRecord, title: string) => Promise<void>;
  }) => (
    <div>
      <div>Sidebar {sessions.length}</div>
      <button type="button" onClick={onNewSession}>New Session</button>
      <button
        type="button"
        onClick={() => {
          const session = sessions[0];
          if (session) void onUpdateSession(session, "Renamed session");
        }}
      >
        Mock rename session
      </button>
    </div>
  ),
}));

vi.mock("./SessionTimeline", () => ({
  SessionTimeline: ({ items }: { items: unknown[] }) => <div>Timeline {items.length}</div>,
}));

vi.mock("./UsageBar", () => ({
  UsageBar: (props: unknown) => {
    usageBarMock(props);
    return <div>Usage Bar</div>;
  },
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
        inputEnabled,
        canCreateSession,
        liveSessionId,
        onSubmit,
        isProcessing,
        canInterrupt,
        isInterrupting,
        onInterrupt,
        restoredInput,
      }: {
        supportsImageInputs: boolean;
        isSubmitting: boolean;
        inputEnabled?: boolean;
        canCreateSession?: boolean;
        liveSessionId?: string | null;
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
        focus: composerFocusMock,
      }));

      return (
        <div>
          <div>Composer images {String(supportsImageInputs)}</div>
          <div>Composer submitting {String(isSubmitting)}</div>
          <div>Composer input enabled {String(inputEnabled)}</div>
          <div>Composer can create {String(canCreateSession)}</div>
          <div>Composer live session {liveSessionId ?? ""}</div>
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
    deleteSession: vi.fn(),
    expandSessionInput: vi.fn(),
    fetchConfigBootstrap: vi.fn(),
    fetchSessionDetail: vi.fn(),
    fetchSessions: vi.fn(),
    sendSessionMessage: vi.fn(),
    setActiveModelProfile: vi.fn(),
    setLiveSessionProfile: vi.fn(),
    updateSession: vi.fn(),
    uploadSavedSessionImages: vi.fn(),
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
        compact_tail_turns: 2,
        compact_preserve_recent_tokens: 8000,
        compact_tool_output_max_chars: 2000,
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
    compact_threshold: 200000,
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
    </Routes>,
    { route },
  );
}

describe("SessionPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useSessionStore.setState({
      activeSessionKey: null,
      sessionsByKey: {},
      liveSessionIndex: {},
      sessionIndex: {},
    });
    vi.mocked(fetchConfigBootstrap).mockResolvedValue(makeConfigBootstrap());
    vi.mocked(fetchSessions).mockResolvedValue([makeSessionRecord()]);
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
    vi.mocked(uploadSavedSessionImages).mockResolvedValue([
      {
        upload_id: "saved-upload-1",
        name: "diagram.png",
        mime_type: "image/png",
        byte_count: 5,
        preview_url: "/api/uploads/saved-upload-1",
      },
    ]);
    vi.mocked(sendSessionMessage).mockResolvedValue(
      makeLiveSession({ live_session_id: "live-new", session_id: "session-1", last_event_seq: 3 }),
    );
    vi.mocked(updateSession).mockResolvedValue(makeSessionRecord({ title: "Renamed session" }));
  });

  afterEach(() => {
    vi.clearAllMocks();
    composerFocusMock.mockClear();
  });

  it("attaches a new run and uploads images through saved-session continuation", async () => {
    const user = userEvent.setup();

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 0")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit Expanded" }));

    await waitFor(() => expect(sendSessionMessage).toHaveBeenCalledTimes(1));
    expect(uploadSavedSessionImages).toHaveBeenCalledWith(
      "session-1",
      expect.arrayContaining([expect.any(File)]),
    );
    expect(sendSessionMessage).toHaveBeenCalledWith("session-1", {
      text: "review @docs and @images/diagram.png",
      file_paths: ["docs/spec.md"],
      image_paths: ["images/diagram.png"],
      image_upload_ids: ["saved-upload-1"],
      profile_id: "analysis",
      interactive_mode: false,
    });
    await waitFor(() => {
      const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
      expect(state?.liveSessionId).toBe("live-new");
      expect(state?.lastEventSeq).toBe(0);
    });
  });

  it("keeps the composer enabled for lazy-created sessions", async () => {
    renderSessionRoute("/sessions");

    expect(await screen.findByText("Composer can create true")).toBeInTheDocument();
    expect(screen.getByText("Composer input enabled true")).toBeInTheDocument();
    expect(screen.getByText("Connection ready")).toBeInTheDocument();
    expect(screen.getByText("Composer live session")).toBeInTheDocument();
    await waitFor(() => expect(composerFocusMock).toHaveBeenCalled());
  });

  it("keeps completed saved sessions sendable without an active live run", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "history-1",
          role: "assistant",
          content: "done",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-04-16T12:00:00Z",
        },
      ],
      active_live_session: null,
      active_run: null,
      timeline: null,
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Composer can create true")).toBeInTheDocument();
    expect(screen.getByText("Composer input enabled true")).toBeInTheDocument();
    expect(screen.getByText("Composer live session")).toBeInTheDocument();
    expect(screen.getByText("Connection ready")).toBeInTheDocument();
  });

  it("keeps previous saved messages visible while hydrating an active run timeline", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "live-processing" }),
      history_items: [
        {
          item_id: "history-1",
          role: "user",
          content: "/plan",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-04-16T12:00:00Z",
        },
        {
          item_id: "history-2",
          role: "assistant",
          content: "Previous plan",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-04-16T12:01:00Z",
        },
        {
          item_id: "history-3",
          role: "user",
          content: "/review",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-04-16T12:02:00Z",
        },
      ],
      active_live_session: makeLiveSession({
        live_session_id: "live-processing",
        session_id: "session-1",
      }),
      timeline: {
        live_session_id: "live-processing",
        session_id: "session-1",
        runtime: null,
        input_enabled: false,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: false,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "message-1",
            role: "user",
            content: "/review",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "thinking-1",
            title: "Thinking",
            content: "reasoning",
          },
        ],
        sub_agents: {},
        last_event_seq: 12,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 4")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "history-2",
      "history-3",
      "thinking-1",
    ]);
  });

  it("dedupes persisted messages from an idle active live timeline", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "idle-live" }),
      history_items: [
        {
          item_id: "history-1",
          role: "user",
          content: "hi",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-03T20:17:33Z",
        },
        {
          item_id: "history-2",
          role: "assistant",
          content: "Hi! What would you like to work on in this repo?",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-03T20:17:38Z",
        },
      ],
      active_live_session: makeLiveSession({
        live_session_id: "idle-live",
        session_id: "session-1",
      }),
      active_run: makeLiveSession({
        live_session_id: "idle-live",
        session_id: "session-1",
      }),
      timeline: {
        live_session_id: "idle-live",
        session_id: "session-1",
        runtime: null,
        input_enabled: true,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: false,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "message-user",
            role: "user",
            content: "hi",
            markdown: false,
          },
          {
            kind: "tool_group",
            itemId: "tool-group-1",
            label: "Tool calls (2)",
            status: "completed",
            items: [],
          },
          {
            kind: "message",
            itemId: "message-assistant",
            role: "assistant",
            content: "Hi! What would you like to work on in this repo?",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 31,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 3")).toBeInTheDocument();
    expect(screen.getByText("Composer live session idle-live")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "history-2",
      "tool-group-1",
    ]);
  });

  it("keeps Kanban-started continuation history in chronological order", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "kanban-continuation" }),
      history_items: [
        {
          item_id: "history-1",
          role: "user",
          content: "/plan\n# Task\ntest task",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-03T01:55:01Z",
        },
        {
          item_id: "history-2",
          role: "assistant",
          content: "this is a test",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-03T01:55:11Z",
        },
        {
          item_id: "history-3",
          role: "user",
          content: "/execute",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-03T01:55:12Z",
        },
        {
          item_id: "history-4",
          role: "assistant",
          content: "this is a test",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-03T01:55:16Z",
        },
        {
          item_id: "history-5",
          role: "user",
          content: "say this is a test again",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-03T19:30:05Z",
        },
      ],
      active_live_session: makeLiveSession({
        live_session_id: "kanban-continuation",
        session_id: "session-1",
      }),
      timeline: {
        live_session_id: "kanban-continuation",
        session_id: "session-1",
        runtime: null,
        input_enabled: false,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: false,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "message-current-user",
            role: "user",
            content: "say this is a test again",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "message-plan",
            role: "user",
            content: "/plan\n# Task\ntest task",
            markdown: false,
            historical: true,
          },
          {
            kind: "message",
            itemId: "message-plan-answer",
            role: "assistant",
            content: "this is a test",
            markdown: true,
            historical: true,
          },
          {
            kind: "message",
            itemId: "message-execute",
            role: "user",
            content: "/execute",
            markdown: false,
            historical: true,
          },
          {
            kind: "message",
            itemId: "message-execute-answer",
            role: "assistant",
            content: "this is a test",
            markdown: true,
            historical: true,
          },
          {
            kind: "thinking",
            itemId: "thinking-current",
            title: "Thinking",
            content: "working",
          },
          {
            kind: "message",
            itemId: "message-current-assistant",
            role: "assistant",
            content: "this is a test",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 8,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 7")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "history-2",
      "history-3",
      "history-4",
      "history-5",
      "thinking-current",
      "message-current-assistant",
    ]);
  });

  it("hydrates dormant web-session projections over saved history without reconnecting", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: null }),
      history_items: [
        {
          item_id: "history-1",
          role: "user",
          content: "hi",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-03T20:10:37Z",
        },
        {
          item_id: "history-2",
          role: "assistant",
          content: "Hi! What would you like to work on in the workspace?",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-03T20:10:41Z",
        },
      ],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "dormant-web-session",
        session_id: "session-1",
        runtime: null,
        input_enabled: true,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: false,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "message-user",
            role: "user",
            content: "hi",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "notice-1",
            role: "notice",
            content: "Retrying... (1/3)",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "thinking-1",
            title: "Working",
            content: "reasoning",
          },
          {
            kind: "message",
            itemId: "message-assistant",
            role: "assistant",
            content: "Hi! What would you like to work on in the workspace?",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 21,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 4")).toBeInTheDocument();
    expect(screen.getByText("Composer live session")).toBeInTheDocument();
    expect(screen.getByText("Composer can create true")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.liveSessionId).toBeNull();
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "history-2",
      "notice-1",
      "thinking-1",
    ]);
  });

  it("hydrates completed saved-session working trace from a persisted timeline", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "history-1",
          role: "assistant",
          content: "done",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-04-16T12:00:00Z",
        },
      ],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "ended-live-1",
        session_id: "session-1",
        runtime: null,
        input_enabled: false,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: true,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "thinking",
            itemId: "thinking-1",
            title: "Thinking",
            content: "reasoning",
          },
          {
            kind: "tool_group",
            itemId: "tool-group-1",
            label: "Tool calls",
            status: "completed",
            items: [{ text: "shell output" }],
          },
        ],
        sub_agents: {},
        last_event_seq: 12,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 2")).toBeInTheDocument();
    expect(screen.getByText("Composer can create true")).toBeInTheDocument();
    expect(screen.getByText("Composer live session")).toBeInTheDocument();
  });

  it("keeps the composer disabled between tool phases until input state enables it", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord(),
      history_items: [],
      active_live_session: makeLiveSession({
        live_session_id: "live-processing",
        session_id: "session-1",
      }),
      timeline: {
        live_session_id: "live-processing",
        session_id: "session-1",
        runtime: null,
        input_enabled: false,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: false,
        fatal_error: null,
        pending_user_questions: null,
        items: [],
        sub_agents: {},
        last_event_seq: 4,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Composer live session live-processing")).toBeInTheDocument();
    expect(screen.getByText("Composer input enabled false")).toBeInTheDocument();
    expect(screen.getByText("Connection disconnected")).toBeInTheDocument();
  });

  it("does not reuse a previous active session on the blank new-session route", async () => {
    useSessionStore.setState({
      activeSessionKey: getSavedSessionKey("session-1"),
      sessionsByKey: {
        [getSavedSessionKey("session-1")]: {
          liveSessionId: "stale-live-1",
          sessionId: "session-1",
          runtime: null,
          connection: "connected",
          inputEnabled: false,
          waitMessage: null,
          processing: null,
          restoredInput: null,
          sessionUsage: null,
          turnUsage: null,
          sessionEnded: true,
          fatalError: null,
          pendingUserQuestions: null,
          items: [],
          itemsVersion: 0,
          subAgents: {},
          lastEventSeq: 3,
        },
      },
      liveSessionIndex: { "stale-live-1": getSavedSessionKey("session-1") },
      sessionIndex: { "session-1": getSavedSessionKey("session-1") },
    });

    renderSessionRoute("/sessions");

    expect(await screen.findByText("Connection ready")).toBeInTheDocument();
    expect(screen.getByText("Composer can create true")).toBeInTheDocument();
    expect(screen.getByText("Composer live session")).toBeInTheDocument();
    expect(vi.mocked(useLiveSessionEvents)).toHaveBeenLastCalledWith(null, null, null);
  });

  it("clears the selected saved session when using the new-session shortcut", async () => {
    const user = userEvent.setup();

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 0")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New Session" }));

    await waitFor(() => {
      expect(screen.getByText("Composer can create true")).toBeInTheDocument();
    });
    expect(screen.getByText("Connection ready")).toBeInTheDocument();
    expect(vi.mocked(useLiveSessionEvents)).toHaveBeenLastCalledWith(null, null, null);
  });

  it("marks direct sends pending and ignores duplicate submits", async () => {
    const user = userEvent.setup();
    let resolveSend!: (session: LiveSession) => void;
    vi.mocked(sendSessionMessage).mockImplementation(
      () =>
        new Promise<LiveSession>((resolve) => {
          resolveSend = resolve;
        }),
    );

    renderSessionRoute("/sessions/session-1");

    await user.click(await screen.findByRole("button", { name: "Submit Expanded" }));

    await waitFor(() => expect(sendSessionMessage).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Composer submitting true")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit Expanded" }));
    expect(sendSessionMessage).toHaveBeenCalledTimes(1);

    resolveSend(
      makeLiveSession({
        live_session_id: "live-new",
        session_id: "session-1",
        last_event_seq: 3,
      }),
    );
    await waitFor(() => {
      expect(screen.getByText("Composer submitting false")).toBeInTheDocument();
    });
  });

  it("renders the saved-session delete icon as a neutral toolbar action with destructive hover styling", async () => {
    renderSessionRoute("/sessions/session-1");

    const deleteButton = await screen.findByRole("button", { name: "Delete session" });

    expect(deleteButton).toHaveAttribute("data-variant", "ghost");
    expect(deleteButton).toHaveAttribute("data-size", "icon-sm");
    expect(deleteButton).toHaveClass("session-topbar__delete-button");
  });

  it("updates saved session titles from the sidebar", async () => {
    const user = userEvent.setup();

    renderSessionRoute("/sessions/session-1");

    await user.click(await screen.findByRole("button", { name: "Mock rename session" }));

    await waitFor(() => {
      expect(updateSession).toHaveBeenCalledWith("session-1", { title: "Renamed session" });
    });
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

});
