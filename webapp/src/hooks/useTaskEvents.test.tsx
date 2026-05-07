import type { PropsWithChildren, ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { useTaskEvents } from "./useTaskEvents";

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

function emitAppEvent(source: MockEventSource, event: Record<string, unknown>) {
  source.onmessage?.(
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
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("invalidates the expected queries for app SSE events", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const source = MockEventSource.instances[0];

    emitAppEvent(source, { type: "task_updated", payload: {}, seq: 1 });
    emitAppEvent(source, { type: "board_stages_updated", payload: {}, seq: 2 });
    emitAppEvent(source, { type: "live_session_ended", payload: {}, seq: 3 });
    emitAppEvent(source, {
      type: "session_updated",
      payload: { session: { session_id: "session-1" } },
      seq: 4,
    });
    emitAppEvent(source, {
      type: "session_created",
      payload: { session: { session_id: "session-2" } },
      seq: 5,
    });

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["tasks"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["board-stages"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["bootstrap"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session", "session-1"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session", "session-2"] });
  });

  it("invalidates session queries for session-created app events", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const source = MockEventSource.instances[0];

    emitAppEvent(source, {
      type: "session_created",
      payload: { session: { session_id: "session-1" } },
      seq: 1,
    });

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["bootstrap"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session", "session-1"] });
  });

  it("returns fresh live-session lifecycle events for notification effects", () => {
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const source = MockEventSource.instances[0];

    act(() => {
      emitAppEvent(source, {
        type: "live_session_started",
        payload: { live_session: { live_session_id: "live-1", status: "starting" } },
        seq: 1,
      });
      emitAppEvent(source, {
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

  it("does not return historical lifecycle events from the app SSE snapshot", () => {
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const source = MockEventSource.instances[0];

    act(() => {
      emitAppEvent(source, {
        created_at: "2026-05-02T11:59:59.000Z",
        type: "live_session_started",
        payload: { live_session: { live_session_id: "live-1", status: "starting" } },
        seq: 1,
      });
    });

    expect(result.current).toHaveLength(0);
  });

  it("closes on SSE errors and reconnects with reset backoff after open", () => {
    const queryClient = new QueryClient();

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const firstSource = MockEventSource.instances[0];
    firstSource.onerror?.();
    expect(firstSource.close).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(999);
    expect(MockEventSource.instances).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(MockEventSource.instances).toHaveLength(2);

    const secondSource = MockEventSource.instances[1];
    secondSource.onopen?.();
    secondSource.onerror?.();

    vi.advanceTimersByTime(999);
    expect(MockEventSource.instances).toHaveLength(2);

    vi.advanceTimersByTime(1);
    expect(MockEventSource.instances).toHaveLength(3);
  });

  it("advances the reconnect cursor for task, board, and session app events", () => {
    const queryClient = new QueryClient();

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const source = MockEventSource.instances[0];

    emitAppEvent(source, { type: "task_updated", payload: {}, seq: 1 });
    emitAppEvent(source, { type: "board_stages_updated", payload: {}, seq: 2 });
    emitAppEvent(source, {
      type: "session_updated",
      payload: { session: { session_id: "session-1" } },
      seq: 3,
    });

    source.onerror?.();
    vi.advanceTimersByTime(1000);

    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1].url).toContain("/api/events/app?since=3");
  });

  it("recovers app snapshots and reconnects from cursor zero after sequence gaps", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const source = MockEventSource.instances[0];

    emitAppEvent(source, { type: "task_updated", payload: {}, seq: 1 });
    emitAppEvent(source, { type: "board_stages_updated", payload: {}, seq: 3 });

    expect(source.close).toHaveBeenCalledTimes(1);
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["tasks"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["board-stages"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["bootstrap"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["dashboard-stats"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["dashboard-runs"] });

    vi.advanceTimersByTime(1000);

    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1].url).toContain("/api/events/app");
    expect(MockEventSource.instances[1].url).not.toContain("since=");
  });

  it("resets the reconnect cursor and invalidates app snapshots after replay-incomplete", () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const source = MockEventSource.instances[0];

    emitAppEvent(source, { type: "task_updated", payload: {}, seq: 1 });
    emitAppEvent(source, {
      type: "server.replay_incomplete",
      payload: {
        reason: "subscriber_queue_overflow",
        requested_since: 12,
        resolved_since: 13,
        latest_seq: 20,
        oldest_available_seq: 18,
        snapshot_required: true,
      },
      seq: 13,
    });

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["tasks"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["board-stages"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["bootstrap"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["dashboard-stats"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["dashboard-runs"] });

    source.onerror?.();
    vi.advanceTimersByTime(1000);

    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1].url).toContain("/api/events/app");
    expect(MockEventSource.instances[1].url).not.toContain("since=");
  });
});
