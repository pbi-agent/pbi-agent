import type { PropsWithChildren, ReactElement } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { useTaskEvents } from "./useTaskEvents";
import {
  resetNotificationPreferencesForTests,
  setNotificationPreferences,
} from "../lib/notificationPreferences";

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

class NotificationMock {
  static instances: NotificationMock[] = [];
  static permission: NotificationPermission = "granted";
  static requestPermission = vi.fn();

  title: string;
  options?: NotificationOptions;
  onclick: ((event: Event) => void) | null = null;
  close = vi.fn();

  constructor(title: string, options?: NotificationOptions) {
    this.title = title;
    this.options = options;
    NotificationMock.instances.push(this);
  }
}

const originalNotification = globalThis.Notification;
const originalVisibilityState = document.visibilityState;
const originalAudioContext = window.AudioContext;

function LocationProbe() {
  const location = useLocation();
  return { pathname: location.pathname };
}

function createWrapper(queryClient: QueryClient, route = "/board") {
  return function Wrapper({ children }: PropsWithChildren): ReactElement {
    return (
      <MemoryRouter initialEntries={[route]}>
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      </MemoryRouter>
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

function emitLiveSessionEnded(socket: MockWebSocket, overrides: Record<string, unknown> = {}) {
  emitAppEvent(socket, {
    type: "live_session_ended",
    payload: {
      live_session: {
        live_session_id: "live-1",
        session_id: "session-1",
        fatal_error: null,
        ...overrides,
      },
    },
    seq: 3,
  });
}

function setWindowAttentionState(hidden: boolean) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: hidden ? "hidden" : "visible",
  });
  vi.spyOn(document, "hasFocus").mockReturnValue(!hidden);
}

describe("useTaskEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-02T12:00:00.000Z"));
    resetNotificationPreferencesForTests();
    MockWebSocket.instances = [];
    NotificationMock.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
    Object.defineProperty(globalThis, "Notification", {
      configurable: true,
      writable: true,
      value: NotificationMock,
    });
    setWindowAttentionState(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    if (originalNotification) {
      Object.defineProperty(globalThis, "Notification", {
        configurable: true,
        writable: true,
        value: originalNotification,
      });
    } else {
      Reflect.deleteProperty(globalThis, "Notification");
    }
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: originalVisibilityState,
    });
    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      writable: true,
      value: originalAudioContext,
    });
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

  it("fires one desktop notification when a live session ends while hidden", () => {
    const queryClient = new QueryClient();
    vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    setNotificationPreferences({ desktopEnabled: true, soundEnabled: false });

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    const socket = MockWebSocket.instances[0];
    act(() => {
      emitLiveSessionEnded(socket);
      emitLiveSessionEnded(socket);
    });

    expect(NotificationMock.instances).toHaveLength(1);
    expect(NotificationMock.instances[0].title).toBe("pbi-agent session finished");
    expect(NotificationMock.instances[0].options?.tag).toBe("session-ended:live-1");
  });

  it("does not fire a session-ended notification for replayed historical events", () => {
    const queryClient = new QueryClient();
    vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    const start = vi.fn();

    class AudioContextMock {
      state = "running" as AudioContextState;
      currentTime = 1;
      destination = {} as AudioDestinationNode;
      close = vi.fn();
      resume = vi.fn();

      createOscillator() {
        return {
          type: "sine" as OscillatorType,
          frequency: {
            setValueAtTime: vi.fn(),
            exponentialRampToValueAtTime: vi.fn(),
          },
          connect: vi.fn(),
          start,
          stop: vi.fn(),
          addEventListener: vi.fn(),
        };
      }

      createGain() {
        return {
          gain: {
            setValueAtTime: vi.fn(),
            exponentialRampToValueAtTime: vi.fn(),
          },
          connect: vi.fn(),
        };
      }
    }

    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      writable: true,
      value: AudioContextMock,
    });
    setNotificationPreferences({ desktopEnabled: true, soundEnabled: true });

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      emitAppEvent(MockWebSocket.instances[0], {
        type: "live_session_ended",
        created_at: "2026-05-02T11:59:59.000Z",
        payload: {
          live_session: {
            live_session_id: "live-1",
            session_id: "session-1",
            fatal_error: null,
          },
        },
        seq: 3,
      });
    });

    expect(NotificationMock.instances).toHaveLength(0);
    expect(start).not.toHaveBeenCalled();
  });

  it("does not fire a session-ended notification while focused", () => {
    const queryClient = new QueryClient();
    vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    setWindowAttentionState(false);
    setNotificationPreferences({ desktopEnabled: true, soundEnabled: false });

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      emitLiveSessionEnded(MockWebSocket.instances[0]);
    });

    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("focuses the window and navigates to the ended session when clicked", () => {
    const queryClient = new QueryClient();
    vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    const focusSpy = vi.spyOn(window, "focus").mockImplementation(() => {});
    setNotificationPreferences({ desktopEnabled: true, soundEnabled: false });

    const { result } = renderHook(() => {
      useTaskEvents();
      return LocationProbe();
    }, {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      emitLiveSessionEnded(MockWebSocket.instances[0]);
      NotificationMock.instances[0].onclick?.(new Event("click"));
    });

    expect(result.current.pathname).toBe("/sessions/session-1");
    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(NotificationMock.instances[0].close).toHaveBeenCalledTimes(1);
  });

  it("plays sound when a live session ends while hidden and sound is enabled", () => {
    const queryClient = new QueryClient();
    vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    const start = vi.fn();
    const stop = vi.fn();
    const connect = vi.fn();
    const setValueAtTime = vi.fn();
    const exponentialRampToValueAtTime = vi.fn();

    class AudioContextMock {
      state = "running" as AudioContextState;
      currentTime = 1;
      destination = {} as AudioDestinationNode;
      close = vi.fn();
      resume = vi.fn();

      createOscillator() {
        return {
          type: "sine" as OscillatorType,
          frequency: { setValueAtTime, exponentialRampToValueAtTime },
          connect,
          start,
          stop,
          addEventListener: vi.fn(),
        };
      }

      createGain() {
        return {
          gain: { setValueAtTime, exponentialRampToValueAtTime },
          connect,
        };
      }
    }

    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      writable: true,
      value: AudioContextMock,
    });
    setNotificationPreferences({ desktopEnabled: false, soundEnabled: true });

    renderHook(() => useTaskEvents(), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      emitLiveSessionEnded(MockWebSocket.instances[0]);
    });

    expect(start).toHaveBeenCalledTimes(1);
    expect(stop).toHaveBeenCalledTimes(1);
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
