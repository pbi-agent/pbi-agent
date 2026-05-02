import { act, screen, waitFor } from "@testing-library/react";
import { useLocation } from "react-router-dom";

import { AskUserNotificationEffects } from "./AskUserNotificationEffects";
import {
  resetNotificationPreferencesForTests,
  setNotificationPreferences,
} from "../../lib/notificationPreferences";
import { getSavedSessionKey, useSessionStore, type SessionRuntimeState } from "../../store";
import { renderWithProviders } from "../../test/render";

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
    pendingUserQuestions: {
      prompt_id: "prompt-1",
      questions: [
        {
          question_id: "question-1",
          question: "Which path should I take?",
          suggestions: ["One", "Two", "Three"],
          recommended_suggestion_index: 0,
        },
      ],
    },
    items: [],
    itemsVersion: 0,
    subAgents: {},
    lastEventSeq: 0,
    ...overrides,
  };
}

function seedPendingQuestion(overrides: Partial<SessionRuntimeState> = {}) {
  const sessionKey = getSavedSessionKey(overrides.sessionId ?? "session-1");
  useSessionStore.setState({
    sessionsByKey: {
      [sessionKey]: makeSessionState(overrides),
    },
    sessionIndex: {
      [overrides.sessionId ?? "session-1"]: sessionKey,
    },
    liveSessionIndex: {
      [overrides.liveSessionId ?? "live-1"]: sessionKey,
    },
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

function renderEffects(route = "/board") {
  return renderWithProviders(
    <>
      <AskUserNotificationEffects />
      <LocationProbe />
    </>,
    { route },
  );
}

describe("AskUserNotificationEffects", () => {
  beforeEach(() => {
    resetNotificationPreferencesForTests();
    NotificationMock.instances = [];
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
    vi.restoreAllMocks();
  });

  it("fires one desktop notification for a new pending question while hidden", async () => {
    seedPendingQuestion();

    const { rerender } = renderEffects();

    await waitFor(() => expect(NotificationMock.instances).toHaveLength(1));
    expect(NotificationMock.instances[0].title).toBe("pbi-agent needs input");
    expect(NotificationMock.instances[0].options?.tag).toBe("ask-user:live-1:prompt-1");

    rerender(
      <>
        <AskUserNotificationEffects />
        <LocationProbe />
      </>,
    );

    expect(NotificationMock.instances).toHaveLength(1);
  });

  it("does not notify while the app is visible and focused", async () => {
    setWindowAttentionState(false);
    seedPendingQuestion();

    renderEffects();

    await waitFor(() => expect(screen.getByTestId("location-path")).toHaveTextContent("/board"));
    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("does not notify when desktop notifications are disabled", async () => {
    setNotificationPreferences({ desktopEnabled: false });
    seedPendingQuestion();

    renderEffects();

    await waitFor(() => expect(screen.getByTestId("location-path")).toHaveTextContent("/board"));
    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("focuses the window and navigates to the waiting session when clicked", async () => {
    const focusSpy = vi.spyOn(window, "focus").mockImplementation(() => {});
    seedPendingQuestion();

    renderEffects();

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

  it("plays sound once for a new hidden pending question when sound is enabled", async () => {
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
    setNotificationPreferences({ desktopEnabled: false, soundEnabled: true, soundId: "pulse" });
    seedPendingQuestion();

    const { rerender } = renderEffects();

    await waitFor(() => expect(start).toHaveBeenCalledTimes(2));
    expect(stop).toHaveBeenCalledTimes(2);

    rerender(
      <>
        <AskUserNotificationEffects />
        <LocationProbe />
      </>,
    );

    expect(start).toHaveBeenCalledTimes(2);
  });
});
