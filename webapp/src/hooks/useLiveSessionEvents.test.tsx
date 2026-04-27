import type { PropsWithChildren, ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { useLiveSessionEvents } from "./useLiveSessionEvents";
import { getSavedSessionKey, useSessionStore } from "../store";

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readonly url: string;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
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
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("updates connection state and forwards websocket messages into the store", () => {
    const queryClient = new QueryClient();
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockWebSocket.instances[0];
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

  it("invalidates run queries when input transitions from disabled to enabled after a saved session turn", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockWebSocket.instances[0];
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

    const socket = MockWebSocket.instances[0];
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

    const socket = MockWebSocket.instances[0];
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

    const socket = MockWebSocket.instances[0];
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

    const firstSocket = MockWebSocket.instances[0];
    firstSocket.onclose?.();

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("disconnected");
    expect(MockWebSocket.instances).toHaveLength(1);

    vi.advanceTimersByTime(1000);
    expect(MockWebSocket.instances).toHaveLength(2);
  });
});
