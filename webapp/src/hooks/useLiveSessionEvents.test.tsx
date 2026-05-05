import type { PropsWithChildren, ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { useLiveSessionEvents } from "./useLiveSessionEvents";
import { getLiveSessionKey, getSavedSessionKey, useSessionStore } from "../store";
import type { LiveSession } from "../types";

class MockEventSource {
  static instances: MockEventSource[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  readonly url: string;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: PropsWithChildren): ReactElement {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

function makeLiveSession(overrides: Partial<LiveSession> = {}): LiveSession {
  return {
    live_session_id: "live-1",
    session_id: "session-1",
    task_id: null,
    kind: "session",
    project_dir: "/workspace",
    created_at: "2026-04-16T12:00:00Z",
    status: "running",
    exit_code: null,
    fatal_error: null,
    ended_at: null,
    last_event_seq: 4,
    provider_id: "openai-main",
    profile_id: "analysis",
    provider: "OpenAI",
    model: "gpt-5.4",
    reasoning_effort: "high",
    compact_threshold: 200000,
    ...overrides,
  };
}

function emit(source: MockEventSource, event: Record<string, unknown>) {
  source.onmessage?.(
    new MessageEvent("message", {
      data: JSON.stringify({
        created_at: "2026-04-27T00:00:00Z",
        ...event,
      }),
    }),
  );
}

describe("useLiveSessionEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useSessionStore.setState({
      activeSessionKey: null,
      sessionsByKey: {},
      liveSessionIndex: {},
      sessionIndex: {},
    });
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
    delete window.__PBI_AGENT_LIVE_DEBUG__;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("updates connection state and forwards SSE messages into the store", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    expect(socket.url).toContain("/api/events/live-1");
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("connecting");

    socket.onopen?.();
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("connected");

    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 1,
          type: "input_state",
          created_at: "2026-04-27T00:00:00Z",
          payload: { enabled: true },
        }),
      }),
    );

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.inputEnabled).toBe(true);
  });

  it("ignores malformed input_state payloads at the stream boundary", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    emit(MockEventSource.instances[0], {
      seq: 1,
      type: "input_state",
      payload: { enabled: "yes" },
    });

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.inputEnabled).toBe(false);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.lastEventSeq).toBe(0);
  });

  it("ignores unknown event types at the stream boundary", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    emit(MockEventSource.instances[0], {
      seq: 1,
      type: "unknown",
      payload: { item_id: "message-1", role: "assistant", content: "ignored" },
    });

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.items).toEqual([]);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.lastEventSeq).toBe(0);
  });

  it("does not connect saved sessions without an active live run", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, null, "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    expect(MockEventSource.instances).toHaveLength(0);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("disconnected");
  });

  it("can stream by stable saved session id when an active run exists", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    expect(socket.url).toContain("/api/events/sessions/session-1");
  });

  it("includes the current live run identity for session-scoped streams", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    const url = new URL(socket.url, window.location.origin);
    expect(url.pathname).toBe("/api/events/sessions/session-1");
    expect(url.searchParams.get("since")).toBe("0");
    expect(url.searchParams.get("live_session_id")).toBe("live-1");
  });

  it("requests only events newer than the current cursor", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.setState({
      activeSessionKey: sessionKey,
      sessionsByKey: {
        [sessionKey]: {
          liveSessionId: "live-1",
          sessionId: "session-1",
          runtime: null,
          connection: "disconnected",
          inputEnabled: false,
          waitMessage: null,
          processing: null,
          restoredInput: null,
          sessionUsage: null,
          turnUsage: null,
          sessionEnded: false,
          fatalError: null,
          pendingUserQuestions: null,
          items: [],
          itemsVersion: 0,
          subAgents: {},
          lastEventSeq: 20,
        },
      },
      liveSessionIndex: { "live-1": sessionKey },
      sessionIndex: { "session-1": sessionKey },
    });

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    expect(socket.url).toContain("/api/events/sessions/session-1?since=20");
  });

  it("records low-noise live-session debug state", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().hydrateSavedSession("session-1", [], 2);
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "live-1", session_id: "session-1", last_event_seq: 2 }),
    );

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const initial = window.__PBI_AGENT_LIVE_DEBUG__?.sessions[sessionKey];
    expect(initial).toEqual(expect.objectContaining({
      sessionKey,
      sessionId: "session-1",
      liveSessionId: "live-1",
      requestedSince: 2,
      cursor: 2,
      connection: "connecting",
    }));
    expect(initial?.clientStreamId).toMatch(/^sse:/);
    expect(initial?.url).toContain("/api/events/sessions/session-1?since=2");

    const socket = MockEventSource.instances[0];
    socket.onopen?.();
    const afterOpen = window.__PBI_AGENT_LIVE_DEBUG__?.sessions[sessionKey];
    expect(afterOpen?.connection).toBe("connected");
    expect(typeof afterOpen?.openedAt).toBe("string");

    emit(socket, {
      seq: 3,
      type: "input_state",
      payload: { enabled: true, session_id: "session-1", live_session_id: "live-1" },
    });

    const afterEvent = window.__PBI_AGENT_LIVE_DEBUG__?.sessions[sessionKey];
    expect(afterEvent?.cursor).toBe(3);
    expect(afterEvent?.lastEvent).toEqual(expect.objectContaining({
      seq: 3,
      type: "input_state",
      targetSessionKey: sessionKey,
      resolvedSessionId: "session-1",
      resolvedLiveSessionId: "live-1",
      applied: true,
    }));
  });

  it("preserves the live session id from session-scoped events", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 1,
          type: "input_state",
          created_at: "2026-04-27T00:00:00Z",
          payload: {
            enabled: false,
            session_id: "session-1",
            live_session_id: "live-1",
          },
        }),
      }),
    );

    const state = useSessionStore.getState();
    expect(state.sessionsByKey[sessionKey]?.liveSessionId).toBe("live-1");
    expect(state.liveSessionIndex["live-1"]).toBe(sessionKey);
  });

  it("applies events for an attached saved-session live stream", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().hydrateSavedSession("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "live-1", session_id: "session-1", last_event_seq: 0 }),
    );

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 1,
          type: "message_added",
          created_at: "2026-04-27T00:00:00Z",
          payload: {
            item_id: "item-1",
            role: "user",
            content: "Hello",
            session_id: "session-1",
            live_session_id: "live-1",
          },
        }),
      }),
    );

    const state = useSessionStore.getState();
    expect(state.sessionsByKey[sessionKey]?.liveSessionId).toBe("live-1");
    expect(state.sessionsByKey[sessionKey]?.items).toHaveLength(1);
    expect(state.sessionsByKey[sessionKey]?.items[0]).toMatchObject({
      kind: "message",
      content: "Hello",
    });
  });

  it("routes a socket event to another saved session by session id", () => {
    const queryClient = new QueryClient();
    const sessionKey1 = getSavedSessionKey("session-1");
    const sessionKey2 = getSavedSessionKey("session-2");
    useSessionStore.getState().hydrateSavedSession("session-1", [], 0);
    useSessionStore.getState().hydrateSavedSession("session-2", [], 0);
    useSessionStore.getState().attachLiveSession(
      sessionKey2,
      makeLiveSession({ live_session_id: "live-2", session_id: "session-2", last_event_seq: 0 }),
    );

    renderHook(() => useLiveSessionEvents(sessionKey1, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    emit(MockEventSource.instances[0], {
      seq: 1,
      type: "message_added",
      payload: {
        session_id: "session-2",
        live_session_id: "live-2",
        item_id: "message-2",
        role: "assistant",
        content: "routed",
      },
    });

    const state = useSessionStore.getState();
    expect(state.sessionsByKey[sessionKey1]?.items).toEqual([]);
    expect(state.sessionsByKey[sessionKey2]?.items).toEqual([
      expect.objectContaining({ itemId: "message-2", content: "routed" }),
    ]);
    expect(state.liveSessionIndex["live-2"]).toBe(sessionKey2);
  });

  it("routes a socket event to another live session by live id", () => {
    const queryClient = new QueryClient();
    const liveKey1 = getLiveSessionKey("live-1");
    const liveKey2 = getLiveSessionKey("live-2");
    useSessionStore.getState().attachLiveSession(
      liveKey1,
      makeLiveSession({ live_session_id: "live-1", session_id: null, last_event_seq: 0 }),
    );
    useSessionStore.getState().attachLiveSession(
      liveKey2,
      makeLiveSession({ live_session_id: "live-2", session_id: null, last_event_seq: 0 }),
    );

    renderHook(() => useLiveSessionEvents(liveKey1, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    emit(MockEventSource.instances[0], {
      seq: 1,
      type: "message_added",
      payload: {
        live_session_id: "live-2",
        item_id: "message-2",
        role: "assistant",
        content: "live routed",
      },
    });

    const state = useSessionStore.getState();
    expect(state.sessionsByKey[liveKey1]?.items).toEqual([]);
    expect(state.sessionsByKey[liveKey2]?.items).toEqual([
      expect.objectContaining({ itemId: "message-2", content: "live routed" }),
    ]);
  });

  it("invalidates run queries when input transitions from disabled to enabled after a saved session turn", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 1,
          type: "input_state",
          created_at: "2026-04-27T00:00:00Z",
          payload: { enabled: false, session_id: "session-1" },
        }),
      }),
    );
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 2,
          type: "input_state",
          created_at: "2026-04-27T00:00:01Z",
          payload: { enabled: true, session_id: "session-1" },
        }),
      }),
    );

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session-runs", "session-1"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["run-detail"] });
  });

  it("does not invalidate run queries for repeated enabled input heartbeats", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 1,
          type: "input_state",
          created_at: "2026-04-27T00:00:00Z",
          payload: { enabled: true, session_id: "session-1" },
        }),
      }),
    );
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 2,
          type: "input_state",
          created_at: "2026-04-27T00:00:01Z",
          payload: { enabled: true, session_id: "session-1" },
        }),
      }),
    );

    invalidateQueries.mockClear();
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 3,
          type: "input_state",
          created_at: "2026-04-27T00:00:02Z",
          payload: { enabled: true, session_id: "session-1" },
        }),
      }),
    );

    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("invalidates run queries when the live session ends", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 1,
          type: "session_state",
          created_at: "2026-04-27T00:00:00Z",
          payload: { state: "ended", session_id: "session-1" },
        }),
      }),
    );

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session-runs", "session-1"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["run-detail"] });
  });

  it("invalidates snapshots and run queries when replay is incomplete", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    emit(socket, {
      seq: 0,
      type: "server.replay_incomplete",
      payload: {
        reason: "cursor_too_old",
        requested_since: 1,
        resolved_since: 1,
        oldest_available_seq: 6,
        latest_seq: 1005,
        snapshot_required: true,
      },
    });

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["bootstrap"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session", "session-1"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session-runs", "session-1"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["run-detail"] });
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.lastEventSeq).toBe(0);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.items).toEqual([]);
  });

  it("ignores malformed replay-incomplete payloads at the stream boundary", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().hydrateSavedSession("session-1", [
      { kind: "message", itemId: "message-1", role: "assistant", content: "keep", markdown: true },
    ], 3);

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    emit(socket, {
      seq: 0,
      type: "server.replay_incomplete",
      payload: {
        reason: "cursor_too_old",
        requested_since: 1,
        resolved_since: 1,
        latest_seq: 1005,
        snapshot_required: "true",
      },
    });

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.items).toEqual([
      expect.objectContaining({ itemId: "message-1" }),
    ]);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.lastEventSeq).toBe(3);
    expect(invalidateQueries).not.toHaveBeenCalled();
    expect(socket.close).not.toHaveBeenCalled();
  });

  it("resets the targeted session when replay is incomplete on another socket", async () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey1 = getSavedSessionKey("session-1");
    const sessionKey2 = getSavedSessionKey("session-2");
    useSessionStore.getState().hydrateSavedSession("session-1", [
      { kind: "message", itemId: "message-1", role: "assistant", content: "keep", markdown: true },
    ], 3);
    useSessionStore.getState().attachLiveSession(
      sessionKey2,
      makeLiveSession({ live_session_id: "live-2", session_id: "session-2", last_event_seq: 8 }),
    );
    useSessionStore.getState().applyEvent(sessionKey2, {
      seq: 9,
      type: "message_added",
      created_at: "2026-04-27T00:00:00Z",
      payload: {
        session_id: "session-2",
        live_session_id: "live-2",
        item_id: "message-2",
        role: "assistant",
        content: "reset",
      },
    });

    renderHook(() => useLiveSessionEvents(sessionKey1, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    emit(socket, {
      seq: 0,
      type: "server.replay_incomplete",
      payload: {
        reason: "cursor_too_old",
        requested_since: 8,
        resolved_since: 0,
        latest_seq: 8,
        snapshot_required: true,
        session_id: "session-2",
        live_session_id: "live-2",
      },
    });

    await act(async () => {
      await Promise.resolve();
    });

    const state = useSessionStore.getState();
    expect(state.sessionsByKey[sessionKey1]?.items).toEqual([
      expect.objectContaining({ itemId: "message-1" }),
    ]);
    expect(state.sessionsByKey[sessionKey1]?.lastEventSeq).toBe(3);
    expect(state.sessionsByKey[sessionKey2]?.items).toEqual([]);
    expect(state.sessionsByKey[sessionKey2]?.lastEventSeq).toBe(0);
    expect(state.sessionsByKey[sessionKey2]?.liveSessionId).toBe("live-2");
    expect(state.sessionsByKey[sessionKey2]?.connection).toBe("disconnected");
    expect(socket.close).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1000);
    expect(MockEventSource.instances).toHaveLength(1);
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session", "session-2"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session-runs", "session-2"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["run-detail"] });
  });

  it("forces snapshot recovery when a session event sequence gap reaches the reducer", async () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().hydrateSavedSession("session-1", [
      { kind: "message", itemId: "message-1", role: "assistant", content: "partial", markdown: true },
    ], 3);
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "live-1", session_id: "session-1", last_event_seq: 3 }),
      { preserveItems: true },
    );

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const firstSocket = MockEventSource.instances[0];
    emit(firstSocket, {
      seq: 5,
      type: "message_added",
      payload: {
        session_id: "session-1",
        live_session_id: "live-1",
        item_id: "message-gap",
        role: "assistant",
        content: "gap",
      },
    });

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.items).toEqual([]);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.lastEventSeq).toBe(0);
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["bootstrap"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session", "session-1"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session-runs", "session-1"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["run-detail"] });
    expect(firstSocket.close).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("recovering");

    await vi.advanceTimersByTimeAsync(1000);

    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1].url).toContain("?since=0");
  });

  it("ignores malformed message_added payloads at the stream boundary", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    emit(MockEventSource.instances[0], {
      seq: 1,
      type: "message_added",
      payload: { item_id: "message-1", role: "assistant" },
    });

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.items).toEqual([]);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.lastEventSeq).toBe(0);
  });

  it("reconnects from cursor zero after replay-incomplete recovery", async () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ last_event_seq: 20 }),
    );

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const firstSocket = MockEventSource.instances[0];
    await act(async () => {
      emit(firstSocket, {
        seq: 0,
        type: "server.replay_incomplete",
        payload: {
          reason: "cursor_ahead",
          requested_since: 20,
          resolved_since: 0,
          latest_seq: 1,
          snapshot_required: true,
        },
      });
      await Promise.resolve();
    });

    expect(firstSocket.close).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("recovering");
    await vi.advanceTimersByTimeAsync(1000);

    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1].url).toContain("?since=0");
    MockEventSource.instances[1].onopen?.();
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("recovered");
  });

  it("keeps store-driven live session identity while recovering from replay-incomplete", async () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ last_event_seq: 20 }),
    );

    renderHook(() => {
      const liveSessionId = useSessionStore(
        (state) => state.sessionsByKey[sessionKey]?.liveSessionId ?? null,
      );
      const sessionId = useSessionStore(
        (state) => state.sessionsByKey[sessionKey]?.sessionId ?? null,
      );
      useLiveSessionEvents(sessionKey, liveSessionId, sessionId);
    }, {
      wrapper: createWrapper(queryClient),
    });

    const firstSocket = MockEventSource.instances[0];
    emit(firstSocket, {
      seq: 0,
      type: "server.replay_incomplete",
      payload: {
        reason: "cursor_ahead",
        requested_since: 20,
        resolved_since: 0,
        latest_seq: 1,
        snapshot_required: true,
      },
    });

    const recoveringState = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(recoveringState?.items).toEqual([]);
    expect(recoveringState?.lastEventSeq).toBe(0);
    expect(recoveringState?.liveSessionId).toBe("live-1");
    expect(firstSocket.close).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1000);

    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1].url).toContain("?since=0");
  });

  it("marks recovery failed when snapshot invalidation fails", async () => {
    const queryClient = new QueryClient();
    vi.spyOn(queryClient, "invalidateQueries").mockRejectedValue(new Error("boom"));
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ last_event_seq: 20 }),
    );

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const firstSocket = MockEventSource.instances[0];
    emit(firstSocket, {
      seq: 0,
      type: "server.replay_incomplete",
      payload: {
        reason: "cursor_ahead",
        requested_since: 20,
        resolved_since: 0,
        latest_seq: 1,
        snapshot_required: true,
      },
    });

    expect(firstSocket.close).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("recovering");
    for (let index = 0; index < 5; index += 1) {
      await Promise.resolve();
    }
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("recovery_failed");
    await vi.advanceTimersByTimeAsync(1000);
    expect(MockEventSource.instances).toHaveLength(1);
  });

  it("invalidates run queries for an attached saved live stream", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "live-1", session_id: "session-1", last_event_seq: 0 }),
    );

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 1,
          type: "input_state",
          created_at: "2026-04-27T00:00:00Z",
          payload: { enabled: false, session_id: "session-1", live_session_id: "live-1" },
        }),
      }),
    );
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 2,
          type: "input_state",
          created_at: "2026-04-27T00:00:02Z",
          payload: { enabled: true, session_id: "session-1", live_session_id: "live-1" },
        }),
      }),
    );

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session-runs", "session-1"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["run-detail"] });
  });

  it("applies server replay events after EventSource reconnect", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().hydrateSavedSession("session-1", [
      { kind: "message", itemId: "message-2", role: "assistant", content: "before", markdown: true },
    ], 2);
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "live-1", session_id: "session-1", last_event_seq: 2 }),
      { preserveItems: true },
    );

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1", "session-1"), {
      wrapper: createWrapper(queryClient),
    });

    const firstSocket = MockEventSource.instances[0];
    firstSocket.onerror?.();
    vi.advanceTimersByTime(1000);

    expect(firstSocket.close).toHaveBeenCalledTimes(1);
    expect(MockEventSource.instances).toHaveLength(2);
    const replaySocket = MockEventSource.instances[1];
    expect(replaySocket.url).toContain("?since=2");

    emit(replaySocket, {
      seq: 3,
      type: "message_added",
      payload: {
        session_id: "session-1",
        live_session_id: "live-1",
        item_id: "message-3",
        role: "assistant",
        content: "replayed one",
      },
    });
    emit(replaySocket, {
      seq: 4,
      type: "message_added",
      payload: {
        session_id: "session-1",
        live_session_id: "live-1",
        item_id: "message-4",
        role: "assistant",
        content: "replayed two",
      },
    });

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state?.lastEventSeq).toBe(4);
    expect(state?.items.map((item) => item.itemId)).toEqual([
      "message-2",
      "message-3",
      "message-4",
    ]);
    expect(invalidateQueries).not.toHaveBeenCalled();
    expect(replaySocket.close).not.toHaveBeenCalled();
  });

  it("reconnects with exponential backoff after close", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    const firstSocket = MockEventSource.instances[0];
    firstSocket.onopen?.();
    firstSocket.onerror?.();

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("reconnecting");
    expect(MockEventSource.instances).toHaveLength(1);

    vi.advanceTimersByTime(1000);
    expect(MockEventSource.instances).toHaveLength(2);
    MockEventSource.instances[1].onopen?.();
    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("recovered");
  });
});
