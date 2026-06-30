import { act, screen, waitFor } from "@testing-library/react";
import { useLocation } from "react-router-dom";

import { SessionFinishedNotificationEffects } from "./SessionFinishedNotificationEffects";
import {
  resetNotificationPreferencesForTests,
  setNotificationPreferences,
} from "../../lib/notificationPreferences";
import { getSavedSessionKey, useSessionStore, type SessionRuntimeState } from "../../store";
import { renderWithProviders } from "../../test/render";
import type { ProcessingState } from "../../types";

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

const WORKING_PROCESSING: ProcessingState = {
  active: true,
  phase: "model_wait",
  message: "Working...",
};

function makeSessionState(
  overrides: Partial<SessionRuntimeState> = {},
): SessionRuntimeState {
  return {
    liveSessionId: "live-1",
    sessionId: "session-1",
    runtime: null,
    connection: "connected",
    inputEnabled: false,
    waitMessage: null,
    processing: null,
    restoredInput: null,
    sessionUsage: null,
    turnUsage: null,
    sessionEnded: false,
    fatalError: null,
    pendingUserQuestions: null,
    queuedFollowUps: [],
    items: [],
    itemsVersion: 0,
    subAgents: {},
    lastEventSeq: 0,
    ...overrides,
  };
}

function setSessionState(overrides: Partial<SessionRuntimeState> = {}) {
  const sessionId = overrides.sessionId ?? "session-1";
  const sessionKey = getSavedSessionKey(sessionId);
  useSessionStore.setState({
    sessionsByKey: {
      [sessionKey]: makeSessionState(overrides),
    },
    sessionIndex: { [sessionId]: sessionKey },
    liveSessionIndex: overrides.liveSessionId
      ? { [overrides.liveSessionId]: sessionKey }
      : {},
  });
}

function setWindowAttentionState(hidden: boolean) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: hidden ? "hidden" : "visible",
  });
  vi.spyOn(document, "hasFocus").mockReturnValue(!hidden);
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-path">{location.pathname}</div>;
}

function effectsUi() {
  return (
    <>
      <SessionFinishedNotificationEffects />
      <LocationProbe />
    </>
  );
}

function renderEffects(route = "/board") {
  return renderWithProviders(effectsUi(), { route });
}

describe("SessionFinishedNotificationEffects", () => {
  beforeEach(() => {
    resetNotificationPreferencesForTests();
    NotificationMock.instances = [];
    useSessionStore.getState().resetAllSessions();
    Object.defineProperty(globalThis, "Notification", {
      configurable: true,
      writable: true,
      value: NotificationMock,
    });
    setWindowAttentionState(true);
    setNotificationPreferences({ desktopEnabled: true, soundEnabled: false });
  });

  afterEach(() => {
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
    useSessionStore.getState().resetAllSessions();
    vi.restoreAllMocks();
  });

  it("notifies once when a working session finishes and re-enables input while hidden", async () => {
    setSessionState({ processing: WORKING_PROCESSING, inputEnabled: false });

    const { rerender } = renderEffects();

    act(() => {
      setSessionState({ processing: null, inputEnabled: true });
    });
    rerender(effectsUi());

    await waitFor(() => expect(NotificationMock.instances).toHaveLength(1));
    expect(NotificationMock.instances[0].title).toBe("pbi-agent session finished");
    expect(NotificationMock.instances[0].options?.body).toBe(
      "A session finished while this tab was hidden or unfocused.",
    );
    expect(NotificationMock.instances[0].options?.tag).toBe("session-finished:live-1");

    rerender(effectsUi());
    expect(NotificationMock.instances).toHaveLength(1);
  });

  it("does not notify for an idle session that was never observed working", async () => {
    setSessionState({ processing: null, inputEnabled: true });

    renderEffects();

    await waitFor(() => expect(screen.getByTestId("location-path")).toHaveTextContent("/board"));
    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("does not notify when the assistant pauses to ask a question", async () => {
    setSessionState({ processing: WORKING_PROCESSING, inputEnabled: false });

    const { rerender } = renderEffects();

    act(() => {
      setSessionState({
        processing: null,
        inputEnabled: false,
        pendingUserQuestions: {
          prompt_id: "prompt-1",
          questions: [
            {
              question_id: "question-1",
              question: "Which path?",
              suggestions: ["a", "b", "c"],
              recommended_suggestion_index: 0,
            },
          ],
        },
      });
    });
    rerender(effectsUi());

    await waitFor(() => expect(screen.getByTestId("location-path")).toHaveTextContent("/board"));
    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("does not notify for a session that ends with a fatal error", async () => {
    setSessionState({ processing: WORKING_PROCESSING, inputEnabled: false });

    const { rerender } = renderEffects();

    act(() => {
      setSessionState({
        processing: null,
        inputEnabled: false,
        sessionEnded: true,
        fatalError: "boom",
      });
    });
    rerender(effectsUi());

    await waitFor(() => expect(screen.getByTestId("location-path")).toHaveTextContent("/board"));
    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("does not notify while the app is visible and focused", async () => {
    setWindowAttentionState(false);
    setSessionState({ processing: WORKING_PROCESSING, inputEnabled: false });

    const { rerender } = renderEffects();

    act(() => {
      setSessionState({ processing: null, inputEnabled: true });
    });
    rerender(effectsUi());

    await waitFor(() => expect(screen.getByTestId("location-path")).toHaveTextContent("/board"));
    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("does not notify when both desktop and sound notifications are disabled", async () => {
    setNotificationPreferences({ desktopEnabled: false, soundEnabled: false });
    setSessionState({ processing: WORKING_PROCESSING, inputEnabled: false });

    const { rerender } = renderEffects();

    act(() => {
      setSessionState({ processing: null, inputEnabled: true });
    });
    rerender(effectsUi());

    await waitFor(() => expect(screen.getByTestId("location-path")).toHaveTextContent("/board"));
    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("focuses the window and navigates to the finished session when clicked", async () => {
    const focusSpy = vi.spyOn(window, "focus").mockImplementation(() => {});
    setSessionState({ processing: WORKING_PROCESSING, inputEnabled: false });

    const { rerender } = renderEffects();

    act(() => {
      setSessionState({ processing: null, inputEnabled: true });
    });
    rerender(effectsUi());

    await waitFor(() => expect(NotificationMock.instances).toHaveLength(1));
    act(() => {
      NotificationMock.instances[0].onclick?.(new Event("click"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("location-path")).toHaveTextContent("/sessions/session-1"),
    );
    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(NotificationMock.instances[0].close).toHaveBeenCalledTimes(1);
  });

  it("plays the notification sound when a hidden session finishes work", async () => {
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
    setNotificationPreferences({ desktopEnabled: false, soundEnabled: true, soundId: "bell" });
    setSessionState({ processing: WORKING_PROCESSING, inputEnabled: false });

    const { rerender } = renderEffects();

    act(() => {
      setSessionState({ processing: null, inputEnabled: true });
    });
    rerender(effectsUi());

    await waitFor(() => expect(start).toHaveBeenCalledTimes(2));
    expect(stop).toHaveBeenCalledTimes(2);
  });
});
