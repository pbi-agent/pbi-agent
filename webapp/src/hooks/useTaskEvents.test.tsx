import type { PropsWithChildren, ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { useTaskEvents } from "./useTaskEvents";

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

function emitAppEvent(socket: MockWebSocket, event: Record<string, unknown>) {
  socket.onmessage?.(
    new MessageEvent("message", {
      data: JSON.stringify({
        created_at: new Date(Date.now() + 1).toISOString(),
        ...event,
      }),
    }),
  );
}

describe("useTaskEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-02T12:00:00.000Z"));
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("invalidates the expected queries for app websocket events", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockWebSocket.instances[0];

    emitAppEvent(socket, { type: "task_updated", payload: {}, seq: 1 });
    emitAppEvent(socket, { type: "board_stages_updated", payload: {}, seq: 2 });
    emitAppEvent(socket, { type: "live_session_ended", payload: {}, seq: 3 });
    emitAppEvent(socket, {
      type: "session_updated",
      payload: { session: { session_id: "session-1" } },
      seq: 4,
    });

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["tasks"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["board-stages"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["bootstrap"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["live-sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session", "session-1"] });
  });

  it("returns fresh live-session lifecycle events for notification effects", () => {
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockWebSocket.instances[0];

    act(() => {
      emitAppEvent(socket, {
        type: "live_session_started",
        payload: { live_session: { live_session_id: "live-1", status: "starting" } },
        seq: 1,
      });
      emitAppEvent(socket, {
        type: "live_session_ended",
        payload: { live_session: { live_session_id: "live-1", status: "ended" } },
        seq: 2,
      });
    });

    expect(result.current).toHaveLength(2);
    expect(result.current.map((event) => event.type)).toEqual([
      "live_session_started",
      "live_session_ended",
    ]);
  });

  it("does not return historical lifecycle events from the app websocket snapshot", () => {
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockWebSocket.instances[0];

    act(() => {
      emitAppEvent(socket, {
        created_at: "2026-05-02T11:59:59.000Z",
        type: "live_session_started",
        payload: { live_session: { live_session_id: "live-1", status: "starting" } },
        seq: 1,
      });
    });

    expect(result.current).toHaveLength(0);
  });

  it("closes on websocket errors and reconnects with reset backoff after open", () => {
    const queryClient = new QueryClient();

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const firstSocket = MockWebSocket.instances[0];
    firstSocket.onerror?.();
    expect(firstSocket.close).toHaveBeenCalledTimes(1);

    firstSocket.onclose?.();
    vi.advanceTimersByTime(999);
    expect(MockWebSocket.instances).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(MockWebSocket.instances).toHaveLength(2);

    const secondSocket = MockWebSocket.instances[1];
    secondSocket.onopen?.();
    secondSocket.onclose?.();

    vi.advanceTimersByTime(999);
    expect(MockWebSocket.instances).toHaveLength(2);

    vi.advanceTimersByTime(1);
    expect(MockWebSocket.instances).toHaveLength(3);
  });
});
