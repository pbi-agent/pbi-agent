import type { PropsWithChildren, ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
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

describe("useTaskEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
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

    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({ type: "task_updated", payload: {}, seq: 1 }),
      }),
    );
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({ type: "board_stages_updated", payload: {}, seq: 2 }),
      }),
    );
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({ type: "live_session_ended", payload: {}, seq: 3 }),
      }),
    );
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          type: "session_updated",
          payload: { session: { session_id: "session-1" } },
          seq: 4,
        }),
      }),
    );

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["tasks"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["board-stages"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["bootstrap"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["live-sessions"] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["session", "session-1"] });
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
