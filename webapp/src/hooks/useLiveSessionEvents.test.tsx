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

describe("useLiveSessionEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("updates connection state and forwards websocket messages into the store", () => {
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"));

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
          payload: { enabled: true },
        }),
      }),
    );

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.inputEnabled).toBe(true);
  });

  it("reconnects with exponential backoff after close", () => {
    const sessionKey = getSavedSessionKey("session-1");

    renderHook(() => useLiveSessionEvents(sessionKey, "live-1"));

    const firstSocket = MockWebSocket.instances[0];
    firstSocket.onclose?.();

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.connection).toBe("disconnected");
    expect(MockWebSocket.instances).toHaveLength(1);

    vi.advanceTimersByTime(1000);
    expect(MockWebSocket.instances).toHaveLength(2);
  });
});
