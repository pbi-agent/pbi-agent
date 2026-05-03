import type { PropsWithChildren, ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { useLiveSessionEvents } from "./useLiveSessionEvents";
import { getSavedSessionKey, useSessionStore } from "../store";

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

  it("accepts the first live id for an already hydrated saved session", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().hydrateSavedSession("session-1");

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

  it("invalidates run queries for a saved session resolved from the live-session index", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const liveKey = "live:live-1";

    renderHook(() => useLiveSessionEvents(liveKey, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockEventSource.instances[0];
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 1,
          type: "input_state",
          created_at: "2026-04-27T00:00:00Z",
          payload: { enabled: false },
        }),
      }),
    );
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 2,
          type: "session_identity",
          created_at: "2026-04-27T00:00:01Z",
          payload: { session_id: "session-1" },
        }),
      }),
    );
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          seq: 3,
          type: "input_state",
          created_at: "2026-04-27T00:00:02Z",
          payload: { enabled: true },
        }),
      }),
    );

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session-runs", "session-1"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["run-detail"] });
  });

  it("reconnects with exponential backoff after close", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    const firstSocket = MockEventSource.instances[0];
    firstSocket.onerror?.();

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("disconnected");
    expect(MockEventSource.instances).toHaveLength(1);

    vi.advanceTimersByTime(1000);
    expect(MockEventSource.instances).toHaveLength(2);
  });
});
