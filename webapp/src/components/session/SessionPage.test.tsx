import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { act, screen, waitFor } from "@testing-library/react";
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
  setActiveModelProfile,
  setSessionProfile,
  submitSessionQuestionResponse,
  updateSession,
  uploadSavedSessionImages,
} from "../../api";
import { createEmptySessionState, getSavedSessionKey, useSessionStore } from "../../store";
import type {
  ConfigBootstrapPayload,
  ExpandedSessionInput,
  LiveSession,
  SessionDetailPayload,
  SessionRecord,
} from "../../types";

const usageBarMock = vi.hoisted(() => vi.fn());
const sessionTimelineMock = vi.hoisted(() => vi.fn());
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
  SessionTimeline: (props: { items: unknown[] }) => {
    sessionTimelineMock(props);
    return <div>Timeline {props.items.length}</div>;
  },
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
    setSessionProfile: vi.fn(),
    setLiveSessionProfile: vi.fn(),
    submitSessionQuestionResponse: vi.fn(),
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
        path="/sessions/:sessionId/sub-agents/:subAgentId"
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
    vi.mocked(submitSessionQuestionResponse).mockResolvedValue(
      makeLiveSession({ live_session_id: "live-question", session_id: "session-1" }),
    );
    vi.mocked(updateSession).mockResolvedValue(makeSessionRecord({ title: "Renamed session" }));
  });

  it("uses the shared app tooltip for the interactive mode toggle", async () => {
    const user = userEvent.setup();
    renderSessionRoute("/sessions/session-1");

    const toggle = await screen.findByRole("button", {
      name: "Toggle interactive mode for assistant questions",
    });
    expect(toggle).not.toHaveAttribute("title");

    await user.hover(toggle);

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent(
      "Allow the assistant to pause and ask questions for each message while this is on.",
    );
    expect(tooltip.closest("[data-app-tooltip]")).not.toBeNull();
  });

  it("renders sub-agent routes as hidden read-only child sessions", async () => {
    useSessionStore.setState((state) => ({
      ...state,
      sessionIndex: { "session-1": getSavedSessionKey("session-1") },
      sessionsByKey: {
        [getSavedSessionKey("session-1")]: {
          ...createEmptySessionState(),
          key: getSavedSessionKey("session-1"),
          sessionId: "session-1",
          connection: "connected",
          items: [
            {
              kind: "message",
              itemId: "parent-msg",
              role: "assistant",
              content: "Parent only",
              markdown: true,
            },
            {
              kind: "message",
              itemId: "sub-msg",
              role: "assistant",
              content: "Sub-agent only",
              markdown: true,
              subAgentId: "sub-1",
            },
          ],
          subAgents: { "sub-1": { title: "Researcher", status: "completed" } },
          itemsVersion: 1,
        },
      },
    }));

    renderSessionRoute("/sessions/session-1/sub-agents/sub-1");

    await screen.findByText("Timeline 1");
    expect(screen.queryByText("Composer images true")).not.toBeInTheDocument();
    expect(screen.queryByText("Interactive")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to main session" })).toHaveAttribute(
      "href",
      "/sessions/session-1",
    );
  });

  it("does not show parent processing as child sub-agent activity", async () => {
    useSessionStore.setState((state) => ({
      ...state,
      sessionIndex: { "session-1": getSavedSessionKey("session-1") },
      sessionsByKey: {
        [getSavedSessionKey("session-1")]: {
          ...createEmptySessionState(),
          key: getSavedSessionKey("session-1"),
          sessionId: "session-1",
          connection: "connected",
          waitMessage: "Parent is still working",
          processing: { active: true, phase: "model_wait", message: "Working" },
          items: [
            {
              kind: "message",
              itemId: "sub-msg",
              role: "assistant",
              content: "Sub-agent done",
              markdown: true,
              subAgentId: "sub-1",
            },
          ],
          subAgents: { "sub-1": { title: "Researcher", status: "completed" } },
          itemsVersion: 1,
        },
      },
    }));

    renderSessionRoute("/sessions/session-1/sub-agents/sub-1");

    await screen.findByText("Timeline 1");
    await waitFor(() => {
      expect(sessionTimelineMock).toHaveBeenLastCalledWith(expect.objectContaining({
        processing: null,
        waitMessage: null,
      }));
    });
  });

  it("does not show an empty working block after a running sub-agent has produced its final response", async () => {
    useSessionStore.setState((state) => ({
      ...state,
      sessionIndex: { "session-1": getSavedSessionKey("session-1") },
      sessionsByKey: {
        [getSavedSessionKey("session-1")]: {
          ...createEmptySessionState(),
          key: getSavedSessionKey("session-1"),
          sessionId: "session-1",
          connection: "connected",
          waitMessage: "Parent is still working",
          processing: { active: true, phase: "tool_execution", message: "Working" },
          items: [
            {
              kind: "message",
              itemId: "sub-user-msg",
              role: "user",
              content: "Delegated task",
              markdown: true,
              subAgentId: "sub-1",
            },
            {
              kind: "message",
              itemId: "sub-final-msg",
              role: "assistant",
              content: "Sub-agent done",
              markdown: true,
              subAgentId: "sub-1",
            },
          ],
          subAgents: { "sub-1": { title: "Researcher", status: "running" } },
          itemsVersion: 1,
        },
      },
    }));

    renderSessionRoute("/sessions/session-1/sub-agents/sub-1");

    await screen.findByText("Timeline 2");
    await waitFor(() => {
      expect(sessionTimelineMock).toHaveBeenLastCalledWith(expect.objectContaining({
        processing: null,
        waitMessage: null,
      }));
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    sessionTimelineMock.mockClear();
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

  it("shows recovery states instead of masking them as ready", async () => {
    const sessionKey = getSavedSessionKey("session-1");
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "live-recovery" }),
      history_items: [],
      active_live_session: makeLiveSession({
        live_session_id: "live-recovery",
        session_id: "session-1",
      }),
      timeline: {
        live_session_id: "live-recovery",
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
        last_event_seq: 3,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Composer live session live-recovery")).toBeInTheDocument();
    const layout = document.querySelector(".session-panel-wrapper");
    expect(layout).toHaveAttribute("data-debug-session-key", sessionKey);
    expect(layout).toHaveAttribute("data-debug-session-id", "session-1");
    expect(layout).toHaveAttribute("data-debug-live-session-id", "live-recovery");
    expect(layout).toHaveAttribute("data-debug-event-cursor", "3");
    expect(layout).toHaveAttribute("data-debug-connection", "disconnected");
    act(() => {
      useSessionStore.getState().setConnection(sessionKey, "recovering");
    });

    await waitFor(() => {
      expect(screen.getByText("Connection recovering")).toBeInTheDocument();
    });
    expect(layout).toHaveAttribute("data-debug-connection", "recovering");
    expect(screen.getByText("Recovering the session from the latest snapshot...")).toBeInTheDocument();

    act(() => {
      useSessionStore.getState().setConnection(sessionKey, "recovery_failed");
    });

    expect(screen.getByText("Connection recovery_failed")).toBeInTheDocument();
    expect(screen.getByText(
      "Unable to recover the live stream. Refresh the session to reload the latest snapshot.",
    )).toBeInTheDocument();
  });

  it("keeps completed saved sessions sendable without an active live run", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
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

  it("detaches a stale saved-session live id when refresh has no live source", async () => {
    const user = userEvent.setup();
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.setState({
      activeSessionKey: sessionKey,
      sessionsByKey: {
        [sessionKey]: {
          ...createEmptySessionState("session-1"),
          liveSessionId: "stale-live",
          connection: "connected",
          items: [
            {
              kind: "message",
              itemId: "stale-message",
              role: "assistant",
              content: "stale local message",
              markdown: true,
            },
          ],
          itemsVersion: 1,
          lastEventSeq: 8,
        },
      },
      liveSessionIndex: { "stale-live": sessionKey },
      sessionIndex: { "session-1": sessionKey },
    });
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
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

    await waitFor(() => {
      const store = useSessionStore.getState();
      const state = store.sessionsByKey[sessionKey];
      expect(state?.liveSessionId).toBeNull();
      expect(state?.connection).toBe("disconnected");
      expect(state?.lastEventSeq).toBe(0);
      expect(store.liveSessionIndex["stale-live"]).toBeUndefined();
    });
    expect(screen.getByText("Composer can create true")).toBeInTheDocument();
    expect(screen.getByText("Composer input enabled true")).toBeInTheDocument();
    expect(screen.getByText("Composer live session")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit Expanded" }));

    await waitFor(() => expect(sendSessionMessage).toHaveBeenCalledTimes(1));
    expect(sendSessionMessage).toHaveBeenCalledWith("session-1", expect.objectContaining({
      text: "review @docs and @images/diagram.png",
    }));
  });

  it("keeps previous saved messages visible while hydrating an active run timeline", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "live-processing" }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
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
          message_id: "msg-2",
          part_ids: { content: "msg-2:content", file_paths: [], image_attachments: [] },
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
          message_id: "msg-3",
          part_ids: { content: "msg-3:content", file_paths: [], image_attachments: [] },
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
        processing: { active: true, phase: "model_wait", message: "Working" },
        session_usage: null,
        turn_usage: null,
        session_ended: false,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "live-plan-user",
            role: "user",
            content: "/plan",
            markdown: false,
            historical: true,
          },
          {
            kind: "message",
            itemId: "live-plan-assistant",
            role: "assistant",
            content: "Previous plan",
            markdown: true,
            historical: true,
          },
          {
            kind: "message",
            itemId: "live-current-user",
            role: "user",
            content: "/review",
            markdown: false,
            historical: true,
          },
          {
            kind: "thinking",
            itemId: "thinking-current",
            title: "Thinking",
            content: "reasoning",
          },
          {
            kind: "message",
            itemId: "message-current-assistant",
            role: "assistant",
            content: "Review result",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 12,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 5")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.liveSessionId).toBe("live-processing");
    expect(state?.lastEventSeq).toBe(12);
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "history-2",
      "history-3",
      "thinking-current",
      "message-current-assistant",
    ]);
    expect(vi.mocked(useLiveSessionEvents)).toHaveBeenCalledWith(
      getSavedSessionKey("session-1"),
      "live-processing",
      "session-1",
    );
  });

  it("dedupes persisted messages from an idle active live timeline", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "idle-live" }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
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
          message_id: "msg-2",
          part_ids: { content: "msg-2:content", file_paths: [], image_attachments: [] },
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
      active_run: null,
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
            messageId: "msg-1",
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
            messageId: "msg-2",
            role: "assistant",
            content: "Hi! What would you like to work on in this repo?",
            markdown: true,
          },
          {
            kind: "message",
            itemId: "message-live-extra",
            role: "assistant",
            content: "New live message",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 31,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 4")).toBeInTheDocument();
    expect(screen.getByText("Composer live session idle-live")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "tool-group-1",
      "history-2",
      "message-live-extra",
    ]);
  });

  it("does not content-match repeated no-id messages to the wrong history item", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "live-repeat" }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "",
          part_ids: { content: "history-1:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "continue",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-05T12:00:00Z",
        },
        {
          item_id: "history-2",
          message_id: "",
          part_ids: { content: "history-2:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "First answer",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-05T12:01:00Z",
        },
        {
          item_id: "history-3",
          message_id: "",
          part_ids: { content: "history-3:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "continue",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-05T12:02:00Z",
        },
      ],
      active_live_session: makeLiveSession({
        live_session_id: "live-repeat",
        session_id: "session-1",
      }),
      active_run: null,
      timeline: {
        live_session_id: "live-repeat",
        session_id: "session-1",
        runtime: null,
        input_enabled: false,
        wait_message: null,
        processing: { active: true, phase: "model_wait", message: "Working" },
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
            content: "continue",
            markdown: false,
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
            content: "Working on it",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 14,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 6")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "history-2",
      "history-3",
      "message-current-user",
      "thinking-current",
      "message-current-assistant",
    ]);
  });

  it("does not content-match a unique no-id live message to older history", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "live-continue" }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "",
          part_ids: { content: "history-1:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "continue",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-05T12:00:00Z",
        },
        {
          item_id: "history-2",
          message_id: "",
          part_ids: { content: "history-2:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "Previous answer",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-05T12:01:00Z",
        },
      ],
      active_live_session: makeLiveSession({
        live_session_id: "live-continue",
        session_id: "session-1",
      }),
      active_run: null,
      timeline: {
        live_session_id: "live-continue",
        session_id: "session-1",
        runtime: null,
        input_enabled: false,
        wait_message: null,
        processing: { active: true, phase: "model_wait", message: "Working" },
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
            content: "continue",
            markdown: false,
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
            content: "Working on it",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 15,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 5")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "history-2",
      "message-current-user",
      "thinking-current",
      "message-current-assistant",
    ]);
  });

  it("keeps refreshed work traces anchored to their original turns", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "history-user-1",
          message_id: "msg-user-1",
          part_ids: { content: "msg-user-1:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "/plan",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-05T12:00:00Z",
        },
        {
          item_id: "history-assistant-1",
          message_id: "msg-assistant-1",
          part_ids: { content: "msg-assistant-1:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "Plan result",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-05T12:01:00Z",
        },
        {
          item_id: "history-user-2",
          message_id: "msg-user-2",
          part_ids: { content: "msg-user-2:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "/review",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-05T12:02:00Z",
        },
        {
          item_id: "history-assistant-2",
          message_id: "msg-assistant-2",
          part_ids: { content: "msg-assistant-2:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "Review result",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-05T12:03:00Z",
        },
      ],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "completed-live-1",
        session_id: "session-1",
        runtime: null,
        input_enabled: true,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: true,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "snapshot-user-1",
            messageId: "msg-user-1",
            role: "user",
            content: "/plan",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "thinking-plan",
            title: "Thinking",
            content: "planning",
          },
          {
            kind: "tool_group",
            itemId: "tool-plan",
            label: "Tool calls",
            status: "completed",
            items: [],
          },
          {
            kind: "message",
            itemId: "snapshot-assistant-1",
            messageId: "msg-assistant-1",
            role: "assistant",
            content: "Plan result",
            markdown: true,
          },
          {
            kind: "message",
            itemId: "snapshot-user-1-replayed",
            messageId: "msg-user-1",
            role: "user",
            content: "/plan",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "snapshot-assistant-1-replayed",
            messageId: "msg-assistant-1",
            role: "assistant",
            content: "Plan result",
            markdown: true,
          },
          {
            kind: "message",
            itemId: "snapshot-user-2",
            messageId: "msg-user-2",
            role: "user",
            content: "/review",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "thinking-review",
            title: "Thinking",
            content: "reviewing",
          },
          {
            kind: "tool_group",
            itemId: "tool-review",
            label: "Tool calls",
            status: "completed",
            items: [],
          },
          {
            kind: "message",
            itemId: "snapshot-assistant-2",
            messageId: "msg-assistant-2",
            role: "assistant",
            content: "Review result",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 24,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 8")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-user-1",
      "thinking-plan",
      "tool-plan",
      "history-assistant-1",
      "history-user-2",
      "thinking-review",
      "tool-review",
      "history-assistant-2",
    ]);
  });

  it("keeps overlapping run work traces before their assistant response", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "msg-1",
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "/plan",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-05T12:00:00Z",
        },
        {
          item_id: "msg-2",
          message_id: "msg-2",
          part_ids: { content: "msg-2:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "this is a test",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-05T12:01:00Z",
        },
        {
          item_id: "msg-3",
          message_id: "msg-3",
          part_ids: { content: "msg-3:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "say again this is a test",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-05T12:02:00Z",
        },
        {
          item_id: "msg-4",
          message_id: "msg-4",
          part_ids: { content: "msg-4:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "this is a test",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-05T12:03:00Z",
        },
      ],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "latest-live",
        session_id: "session-1",
        runtime: null,
        input_enabled: true,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: true,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "msg-1",
            messageId: "msg-1",
            role: "user",
            content: "/plan",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "thinking-plan",
            title: "Thinking",
            content: "planning",
          },
          {
            kind: "message",
            itemId: "msg-2",
            messageId: "msg-2",
            role: "assistant",
            content: "this is a test",
            markdown: true,
          },
          {
            kind: "message",
            itemId: "msg-1-replayed",
            messageId: "msg-1",
            role: "user",
            content: "/plan",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "msg-2-replayed",
            messageId: "msg-2",
            role: "assistant",
            content: "this is a test",
            markdown: true,
          },
          {
            kind: "message",
            itemId: "msg-3",
            messageId: "msg-3",
            role: "user",
            content: "say again this is a test",
            markdown: false,
          },
          {
            kind: "thinking",
            itemId: "thinking-repeat",
            title: "Thinking",
            content: "repeating",
          },
          {
            kind: "message",
            itemId: "msg-4",
            messageId: "msg-4",
            role: "assistant",
            content: "this is a test",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 28,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 6")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "msg-1",
      "thinking-plan",
      "msg-2",
      "msg-3",
      "thinking-repeat",
      "msg-4",
    ]);
  });

  it("keeps duplicate historical work traces anchored before later saved messages", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "history-user-1",
          message_id: "msg-user-1",
          part_ids: { content: "msg-user-1:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "run the test",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-05T12:00:00Z",
        },
        {
          item_id: "history-assistant-1",
          message_id: "msg-assistant-1",
          part_ids: { content: "msg-assistant-1:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "this is a test",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-05T12:01:00Z",
        },
        {
          item_id: "history-user-2",
          message_id: "msg-user-2",
          part_ids: { content: "msg-user-2:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "run it again",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-05T12:02:00Z",
        },
        {
          item_id: "history-assistant-2",
          message_id: "msg-assistant-2",
          part_ids: { content: "msg-assistant-2:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "this is a test",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-05T12:03:00Z",
        },
        {
          item_id: "history-assistant-final",
          message_id: "msg-assistant-final",
          part_ids: { content: "msg-assistant-final:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "final answer",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-05T12:04:00Z",
        },
      ],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "historical-run-1",
        session_id: "session-1",
        runtime: null,
        input_enabled: true,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: true,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "historical-run-1:assistant-1",
            role: "assistant",
            content: "this is a test",
            markdown: true,
            historical: true,
          },
          {
            kind: "tool_group",
            itemId: "historical-run-1:tool-group-8",
            label: "Tool calls",
            status: "completed",
            items: [],
          },
          {
            kind: "message",
            itemId: "historical-run-1:assistant-duplicate",
            role: "assistant",
            content: "this is a test",
            markdown: true,
            historical: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 32,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 6")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-user-1",
      "history-assistant-1",
      "historical-run-1:tool-group-8",
      "history-user-2",
      "history-assistant-2",
      "history-assistant-final",
    ]);
  });

  it("keeps pre-compaction work traces before later active-run messages", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "review-run" }),
      history_items: [
        {
          item_id: "compact-system",
          message_id: "msg-compact-system",
          part_ids: { content: "msg-compact-system:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "[compacted context]",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-08T08:57:15Z",
        },
        {
          item_id: "compact-reference",
          message_id: "msg-compact-reference",
          part_ids: { content: "msg-compact-reference:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "[compacted context — reference only] summary",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-08T08:57:15Z",
        },
        {
          item_id: "history-user-original",
          message_id: "msg-user-after-compact",
          part_ids: { content: "msg-user-after-compact:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "refactor the navigation",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-08T08:57:15Z",
        },
        {
          item_id: "history-assistant-summary",
          message_id: "msg-assistant-after-compact",
          part_ids: { content: "msg-assistant-after-compact:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "refactor complete",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-08T09:03:13Z",
        },
        {
          item_id: "history-user-review",
          message_id: "msg-user-review",
          part_ids: { content: "msg-user-review:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "/review",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-08T09:15:52Z",
        },
        {
          item_id: "history-assistant-review",
          message_id: "msg-assistant-review",
          part_ids: { content: "msg-assistant-review:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "review findings",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-08T09:18:06Z",
        },
      ],
      active_live_session: null,
      active_run: makeLiveSession({ live_session_id: "review-run", session_id: "session-1" }),
      timeline: {
        live_session_id: "review-run",
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
            itemId: "completed-run:old-user",
            message_id: "msg-stale-user-before-compact",
            role: "user",
            content: "refactor the navigation",
            markdown: false,
            historical: true,
          },
          {
            kind: "tool_group",
            itemId: "completed-run:tool-group-1",
            label: "Tool calls",
            status: "completed",
            items: [],
          },
          {
            kind: "message",
            itemId: "completed-run:old-assistant",
            message_id: "msg-assistant-after-compact",
            role: "assistant",
            content: "refactor complete",
            markdown: true,
            historical: true,
          },
          {
            kind: "message",
            itemId: "history-user-review",
            message_id: "msg-user-review",
            role: "user",
            content: "/review",
            markdown: false,
          },
          {
            kind: "tool_group",
            itemId: "tool-group-review",
            label: "Tool calls",
            status: "completed",
            items: [],
          },
          {
            kind: "message",
            itemId: "history-assistant-review",
            message_id: "msg-assistant-review",
            role: "assistant",
            content: "review findings",
            markdown: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 100,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 8")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "completed-run:old-user",
      "completed-run:tool-group-1",
      "compact-system",
      "compact-reference",
      "history-assistant-summary",
      "history-user-review",
      "tool-group-review",
      "history-assistant-review",
    ]);
  });

  it("preserves pre-compaction messages whose rewritten tail has the same content", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended" }),
      history_items: [
        {
          item_id: "compact-system",
          message_id: "msg-compact-system",
          part_ids: { content: "msg-compact-system:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "[compacted context]",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-08T08:57:15Z",
        },
        {
          item_id: "compact-reference",
          message_id: "msg-compact-reference",
          part_ids: { content: "msg-compact-reference:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "[compacted context — reference only] summary",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-08T08:57:15Z",
        },
        {
          item_id: "history-user-rewritten-tail",
          message_id: "msg-rewritten-tail",
          part_ids: { content: "msg-rewritten-tail:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "analyse the current branch edit",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-08T08:57:15Z",
        },
        {
          item_id: "history-assistant-after-compact",
          message_id: "msg-assistant-after-compact",
          part_ids: { content: "msg-assistant-after-compact:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "final answer after compaction",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-08T09:03:13Z",
        },
      ],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "combined-history",
        session_id: "session-1",
        runtime: null,
        input_enabled: true,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: true,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "completed-run:old-user-before-compact",
            message_id: "msg-deleted-before-compact",
            role: "user",
            content: "analyse the current branch edit",
            markdown: false,
            historical: true,
            created_at: "2026-05-08T08:47:17Z",
          },
          {
            kind: "tool_group",
            itemId: "completed-run:tool-group-before-compact",
            label: "Tool calls",
            status: "completed",
            items: [],
          },
          {
            kind: "message",
            itemId: "later-run:history-user-rewritten-tail",
            message_id: "msg-rewritten-tail",
            role: "user",
            content: "analyse the current branch edit",
            markdown: false,
            historical: true,
            created_at: "2026-05-08T08:57:15Z",
          },
          {
            kind: "message",
            itemId: "history-assistant-after-compact",
            message_id: "msg-assistant-after-compact",
            role: "assistant",
            content: "final answer after compaction",
            markdown: true,
            historical: true,
          },
        ],
        sub_agents: {},
        last_event_seq: 100,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 5")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "completed-run:old-user-before-compact",
      "completed-run:tool-group-before-compact",
      "compact-system",
      "compact-reference",
      "history-assistant-after-compact",
    ]);
  });

  it("anchors post-compaction stale snapshot messages by signature", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended" }),
      history_items: [
        {
          item_id: "compact-system",
          message_id: "msg-compact-system",
          part_ids: { content: "msg-compact-system:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "[compacted context]",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-08T08:57:15Z",
        },
        {
          item_id: "history-user-after-compact",
          message_id: "msg-user-after-compact-rewritten",
          part_ids: { content: "msg-user-after-compact-rewritten:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "fix the compacted session display",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-05-08T09:00:00Z",
        },
        {
          item_id: "history-assistant-after-compact",
          message_id: "msg-assistant-after-compact-rewritten",
          part_ids: { content: "msg-assistant-after-compact-rewritten:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "display fixed",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-05-08T09:03:13Z",
        },
      ],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "combined-history",
        session_id: "session-1",
        runtime: null,
        input_enabled: true,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: true,
        fatal_error: null,
        pending_user_questions: null,
        items: [
          {
            kind: "message",
            itemId: "completed-run:stale-user-after-compact",
            message_id: "msg-stale-user-after-compact",
            role: "user",
            content: "fix the compacted session display",
            markdown: false,
            historical: true,
            created_at: "2026-05-08T09:00:00Z",
          },
          {
            kind: "message",
            itemId: "history-assistant-after-compact",
            message_id: "msg-assistant-after-compact-rewritten",
            role: "assistant",
            content: "display fixed",
            markdown: true,
            historical: true,
            created_at: "2026-05-08T09:03:13Z",
          },
        ],
        sub_agents: {},
        last_event_seq: 100,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 3")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "compact-system",
      "history-user-after-compact",
      "history-assistant-after-compact",
    ]);
  });

  it("keeps Kanban-started continuation history in chronological order", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "running", active_run_id: "kanban-continuation" }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
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
          message_id: "msg-2",
          part_ids: { content: "msg-2:content", file_paths: [], image_attachments: [] },
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
          message_id: "msg-3",
          part_ids: { content: "msg-3:content", file_paths: [], image_attachments: [] },
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
          message_id: "msg-4",
          part_ids: { content: "msg-4:content", file_paths: [], image_attachments: [] },
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
          message_id: "msg-5",
          part_ids: { content: "msg-5:content", file_paths: [], image_attachments: [] },
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

    expect(await screen.findByText("Timeline 8")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "history-2",
      "history-3",
      "history-4",
      "history-5",
      "message-current-user",
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
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
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
          message_id: "msg-2",
          part_ids: { content: "msg-2:content", file_paths: [], image_attachments: [] },
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
      "notice-1",
      "thinking-1",
      "history-2",
    ]);
  });

  it("hydrates completed saved-session working trace from a persisted timeline", async () => {
    const user = userEvent.setup();

    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
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

    expect(await screen.findByText("Timeline 3")).toBeInTheDocument();
    expect(screen.getByText("Composer can create true")).toBeInTheDocument();
    expect(screen.getByText("Composer live session")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "thinking-1",
      "tool-group-1",
    ]);
    expect(state?.liveSessionId).toBeNull();
    expect(vi.mocked(useLiveSessionEvents)).toHaveBeenCalledWith(
      getSavedSessionKey("session-1"),
      null,
      "session-1",
    );

    await user.click(screen.getByRole("button", { name: "Submit Expanded" }));
    await waitFor(() => expect(sendSessionMessage).toHaveBeenCalledTimes(1));
    expect(sendSessionMessage).toHaveBeenCalledWith("session-1", {
      text: "review @docs and @images/diagram.png",
      file_paths: ["docs/spec.md"],
      image_paths: ["images/diagram.png"],
      image_upload_ids: ["saved-upload-1"],
      profile_id: "analysis",
      interactive_mode: false,
    });
  });

  it("allows changing the profile for a dormant saved session after restart", async () => {
    const user = userEvent.setup();
    const baseConfig = makeConfigBootstrap();
    const analysisProfile = baseConfig.model_profiles[0];
    const reviewProfile = {
      ...analysisProfile,
      id: "review",
      name: "Review",
      model: "gpt-5.4-mini",
      is_active_default: false,
      resolved_runtime: {
        ...analysisProfile.resolved_runtime,
        profile_id: "review",
        model: "gpt-5.4-mini",
      },
    };

    vi.mocked(fetchConfigBootstrap).mockResolvedValue({
      ...baseConfig,
      model_profiles: [analysisProfile, reviewProfile],
    });
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "completed-live-1",
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
        items: [],
        sub_agents: {},
        last_event_seq: 12,
      },
    } satisfies SessionDetailPayload);
    vi.mocked(setSessionProfile).mockResolvedValue(makeLiveSession({
      live_session_id: "session-1",
      session_id: "session-1",
      status: "idle",
      profile_id: "review",
      model: "gpt-5.4-mini",
    }));

    renderSessionRoute("/sessions/session-1");

    const trigger = await screen.findByRole("button", { name: "Model profile: Analysis" });
    expect(trigger).toBeEnabled();
    await user.click(trigger);
    await user.click(await screen.findByText("Review"));

    await waitFor(() => expect(setSessionProfile).toHaveBeenCalledWith("session-1", "review"));
    expect(setActiveModelProfile).not.toHaveBeenCalled();
  });

  it("keeps blank-session profile changes on the active default", async () => {
    const user = userEvent.setup();
    const baseConfig = makeConfigBootstrap();
    const analysisProfile = baseConfig.model_profiles[0];
    const reviewProfile = {
      ...analysisProfile,
      id: "review",
      name: "Review",
      model: "gpt-5.4-mini",
      is_active_default: false,
      resolved_runtime: {
        ...analysisProfile.resolved_runtime,
        profile_id: "review",
        model: "gpt-5.4-mini",
      },
    };

    vi.mocked(fetchConfigBootstrap).mockResolvedValue({
      ...baseConfig,
      model_profiles: [analysisProfile, reviewProfile],
    });
    vi.mocked(setActiveModelProfile).mockResolvedValue({
      active_profile_id: "review",
      config_revision: "rev-2",
    });

    renderSessionRoute("/sessions");

    const trigger = await screen.findByRole("button", { name: "Model profile: Analysis" });
    await user.click(trigger);
    await user.click(await screen.findByText("Review"));

    await waitFor(() => expect(setActiveModelProfile).toHaveBeenCalledWith("review", "rev-1"));
    expect(setSessionProfile).not.toHaveBeenCalled();
  });

  it("dedupes dormant timeline overlays by historical ids and signatures", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "hi",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-04-16T12:00:00Z",
        },
        {
          item_id: "history-2",
          message_id: "msg-2",
          part_ids: { content: "msg-2:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "hello",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-04-16T12:01:00Z",
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
            kind: "message",
            itemId: "history-1",
            role: "user",
            content: "hi",
            markdown: false,
          },
          {
            kind: "message",
            itemId: "live-assistant-copy",
            role: "assistant",
            content: "hello",
            markdown: true,
          },
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
            items: [],
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
      "thinking-1",
      "tool-group-1",
    ]);
    expect(state?.liveSessionId).toBeNull();
  });

  it("merges completed Kanban timelines with saved history without duplicates", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "ended", active_run_id: null }),
      history_items: [
        {
          item_id: "history-1",
          message_id: "msg-1",
          part_ids: { content: "msg-1:content", file_paths: [], image_attachments: [] },
          role: "user",
          content: "Investigate",
          file_paths: [],
          image_attachments: [],
          markdown: false,
          historical: true,
          created_at: "2026-04-16T12:00:00Z",
        },
        {
          item_id: "history-2",
          message_id: "msg-2",
          part_ids: { content: "msg-2:content", file_paths: [], image_attachments: [] },
          role: "assistant",
          content: "Done.",
          file_paths: [],
          image_attachments: [],
          markdown: true,
          historical: true,
          created_at: "2026-04-16T12:01:00Z",
        },
      ],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "task-live-1",
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
            kind: "message",
            itemId: "message-1",
            role: "assistant",
            content: "Done.",
            markdown: true,
          },
          {
            kind: "thinking",
            itemId: "thinking-1",
            title: "Thinking",
            content: "reasoning",
          },
        ],
        sub_agents: {},
        last_event_seq: 9,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Timeline 3")).toBeInTheDocument();
    expect(screen.getByText("Composer can create true")).toBeInTheDocument();
    expect(screen.getByText("Composer live session")).toBeInTheDocument();
    const state = useSessionStore.getState().sessionsByKey[getSavedSessionKey("session-1")];
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "history-1",
      "history-2",
      "thinking-1",
    ]);
    expect(state?.liveSessionId).toBeNull();
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

  it("submits hydrated pending questions through the saved-session endpoint", async () => {
    const user = userEvent.setup();

    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "waiting_for_input", active_run_id: "live-question" }),
      history_items: [],
      active_live_session: makeLiveSession({
        live_session_id: "live-question",
        session_id: "session-1",
        status: "waiting_for_input",
      }),
      timeline: {
        live_session_id: "live-question",
        session_id: "session-1",
        runtime: null,
        input_enabled: false,
        wait_message: null,
        processing: { active: true, phase: "model_wait", message: "Waiting for input" },
        session_usage: null,
        turn_usage: null,
        session_ended: false,
        fatal_error: null,
        pending_user_questions: {
          prompt_id: "ask-1",
          questions: [
            {
              question_id: "q-1",
              question: "Which API style should I use?",
              suggestions: ["Use REST", "Use GraphQL", "Use SSE"],
              recommended_suggestion_index: 0,
            },
          ],
        },
        items: [],
        sub_agents: {},
        last_event_seq: 7,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("Assistant needs your input")).toBeInTheDocument();
    expect(screen.getByText("Which API style should I use?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Send answers" }));

    await waitFor(() => expect(submitSessionQuestionResponse).toHaveBeenCalledTimes(1));
    expect(submitSessionQuestionResponse).toHaveBeenCalledWith("session-1", {
      prompt_id: "ask-1",
      answers: [
        {
          question_id: "q-1",
          answer: "Use REST",
          selected_suggestion_index: 0,
          custom: false,
        },
      ],
    });
  });

  it("surfaces fatal errors from hydrated session timelines", async () => {
    vi.mocked(fetchSessionDetail).mockResolvedValue({
      session: makeSessionRecord({ status: "failed", active_run_id: null }),
      history_items: [],
      active_live_session: null,
      active_run: null,
      timeline: {
        live_session_id: "failed-live",
        session_id: "session-1",
        runtime: null,
        input_enabled: true,
        wait_message: null,
        processing: null,
        session_usage: null,
        turn_usage: null,
        session_ended: true,
        fatal_error: "RuntimeError: boom",
        pending_user_questions: null,
        items: [],
        sub_agents: {},
        last_event_seq: 4,
      },
    } satisfies SessionDetailPayload);

    renderSessionRoute("/sessions/session-1");

    expect(await screen.findByText("RuntimeError: boom")).toBeInTheDocument();
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

  it("does not render a saved-session delete action in the top toolbar", async () => {
    renderSessionRoute("/sessions/session-1");

    await screen.findByText("Run History session-1");

    expect(screen.queryByRole("button", { name: "Delete session" })).not.toBeInTheDocument();
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
