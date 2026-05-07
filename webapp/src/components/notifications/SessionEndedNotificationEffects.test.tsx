import { act, screen, waitFor } from "@testing-library/react";
import { useLocation } from "react-router-dom";

import { SessionEndedNotificationEffects } from "./SessionEndedNotificationEffects";
import {
  resetNotificationPreferencesForTests,
  setNotificationPreferences,
} from "../../lib/notificationPreferences";
import { renderWithProviders } from "../../test/render";
import type { LiveSession, LiveSessionLifecycleEvent, TaskRecord } from "../../types";

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

function makeLiveSession(overrides: Partial<LiveSession> = {}): LiveSession {
  return {
    live_session_id: "live-1",
    session_id: "session-1",
    task_id: null,
    kind: "session",
    project_dir: "/workspace",
    created_at: "2026-05-02T12:00:00.000Z",
    status: "running",
    exit_code: null,
    fatal_error: null,
    ended_at: null,
    last_event_seq: 1,
    provider_id: null,
    profile_id: null,
    provider: "openai",
    model: "gpt-4.1",
    reasoning_effort: "medium",
    compact_threshold: 0.5,
    ...overrides,
  };
}

function makeTaskRecord(overrides: Partial<TaskRecord> = {}): TaskRecord {
  return {
    task_id: "task-1",
    directory: "/workspace",
    title: "Fix login bug",
    prompt: "Fix the login bug",
    stage: "done",
    position: 1,
    project_dir: "/workspace",
    session_id: "session-1",
    profile_id: null,
    run_status: "completed",
    last_result_summary: "",
    created_at: "2026-05-02T12:00:00.000Z",
    updated_at: "2026-05-02T12:01:00.000Z",
    last_run_started_at: "2026-05-02T12:00:00.000Z",
    last_run_finished_at: "2026-05-02T12:01:00.000Z",
    image_attachments: [],
    runtime_summary: {
      provider: "openai",
      provider_id: null,
      profile_id: null,
      model: "gpt-4.1",
      reasoning_effort: "medium",
      compact_threshold: 0.5,
    },
    ...overrides,
  };
}

function makeLifecycleEvent(
  seq: number,
  type: LiveSessionLifecycleEvent["type"],
  liveSession: LiveSession,
): LiveSessionLifecycleEvent {
  return {
    seq,
    type,
    created_at: `2026-05-02T12:00:0${seq}.000Z`,
    live_session: liveSession,
  };
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

function renderEffects(
  liveSessions: LiveSession[],
  route = "/board",
  liveSessionEvents: LiveSessionLifecycleEvent[] = [],
  tasks: TaskRecord[] = [],
) {
  return renderWithProviders(
    <>
      <SessionEndedNotificationEffects
        liveSessionEvents={liveSessionEvents}
        liveSessions={liveSessions}
        tasks={tasks}
      />
      <LocationProbe />
    </>,
    { route },
  );
}

function effectsUi(
  liveSessions: LiveSession[],
  liveSessionEvents: LiveSessionLifecycleEvent[] = [],
  tasks: TaskRecord[] = [],
) {
  return (
    <>
      <SessionEndedNotificationEffects
        liveSessionEvents={liveSessionEvents}
        liveSessions={liveSessions}
        tasks={tasks}
      />
      <LocationProbe />
    </>
  );
}

describe("SessionEndedNotificationEffects", () => {
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

  it("does not notify for already-ended sessions on first render", async () => {
    renderEffects([
      makeLiveSession({
        status: "ended",
        ended_at: "2026-05-02T12:01:00.000Z",
      }),
    ]);

    await waitFor(() => expect(screen.getByTestId("location-path")).toHaveTextContent("/board"));
    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("notifies once when an observed running session transitions to ended while hidden", async () => {
    const running = makeLiveSession({ status: "running", last_event_seq: 1 });
    const ended = makeLiveSession({
      status: "ended",
      ended_at: "2026-05-02T12:01:00.000Z",
      last_event_seq: 2,
    });
    const { rerender } = renderEffects([running]);

    rerender(effectsUi([ended]));

    await waitFor(() => expect(NotificationMock.instances).toHaveLength(1));
    expect(NotificationMock.instances[0].title).toBe("pbi-agent session finished");
    expect(NotificationMock.instances[0].options?.body).toBe(
      "A session finished while this tab was hidden or unfocused.",
    );
    expect(NotificationMock.instances[0].options?.tag).toBe("session-ended:live-1");

    rerender(effectsUi([ended]));
    expect(NotificationMock.instances).toHaveLength(1);
  });

  it("includes the task title when an observed kanban task session transitions to ended while hidden", async () => {
    const focusSpy = vi.spyOn(window, "focus").mockImplementation(() => {});
    const task = makeTaskRecord({ title: "Ship kanban notifications" });
    const running = makeLiveSession({
      kind: "task",
      task_id: task.task_id,
      status: "running",
      last_event_seq: 1,
    });
    const ended = makeLiveSession({
      kind: "task",
      task_id: task.task_id,
      status: "ended",
      ended_at: "2026-05-02T12:01:00.000Z",
      last_event_seq: 2,
    });
    const { rerender } = renderEffects([running], "/board", [], [task]);

    rerender(effectsUi([ended], [], [task]));

    await waitFor(() => expect(NotificationMock.instances).toHaveLength(1));
    expect(NotificationMock.instances[0].title).toBe("pbi-agent session finished");
    expect(NotificationMock.instances[0].options?.body).toBe(
      "“Ship kanban notifications” finished while this tab was hidden or unfocused.",
    );

    act(() => {
      NotificationMock.instances[0].onclick?.(new Event("click"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("location-path")).toHaveTextContent("/sessions/session-1"),
    );
    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(NotificationMock.instances[0].close).toHaveBeenCalledTimes(1);
  });

  it("uses the generic finished notification when a kanban task record is missing", async () => {
    const running = makeLiveSession({
      kind: "task",
      task_id: "missing-task",
      status: "running",
      last_event_seq: 1,
    });
    const ended = makeLiveSession({
      kind: "task",
      task_id: "missing-task",
      status: "ended",
      ended_at: "2026-05-02T12:01:00.000Z",
      last_event_seq: 2,
    });
    const { rerender } = renderEffects([running]);

    rerender(effectsUi([ended]));

    await waitFor(() => expect(NotificationMock.instances).toHaveLength(1));
    expect(NotificationMock.instances[0].options?.body).toBe(
      "A session finished while this tab was hidden or unfocused.",
    );
  });

  it("uses fresh lifecycle events before dropping ended bootstrap snapshots", async () => {
    const starting = makeLiveSession({ status: "starting", last_event_seq: 1 });
    const ended = makeLiveSession({
      status: "ended",
      ended_at: "2026-05-02T12:01:00.000Z",
      last_event_seq: 2,
    });
    const { rerender } = renderEffects([]);

    rerender(effectsUi([ended], [
      makeLifecycleEvent(1, "live_session_started", starting),
      makeLifecycleEvent(2, "live_session_ended", ended),
    ]));

    await waitFor(() => expect(NotificationMock.instances).toHaveLength(1));
    expect(NotificationMock.instances[0].options?.tag).toBe("session-ended:live-1");
  });

  it("does not notify for a focused transition and does not notify later after blur", async () => {
    setWindowAttentionState(false);
    const running = makeLiveSession({ status: "running", last_event_seq: 1 });
    const ended = makeLiveSession({
      status: "ended",
      ended_at: "2026-05-02T12:01:00.000Z",
      last_event_seq: 2,
    });
    const { rerender } = renderEffects([running]);

    rerender(effectsUi([ended]));
    await waitFor(() => expect(screen.getByTestId("location-path")).toHaveTextContent("/board"));
    expect(NotificationMock.instances).toHaveLength(0);

    setWindowAttentionState(true);
    rerender(effectsUi([ended]));
    expect(NotificationMock.instances).toHaveLength(0);
  });

  it("focuses the window and navigates to the saved session when clicked", async () => {
    const focusSpy = vi.spyOn(window, "focus").mockImplementation(() => {});
    const { rerender } = renderEffects([makeLiveSession({ status: "running" })]);

    rerender(effectsUi([
      makeLiveSession({
        status: "ended",
        ended_at: "2026-05-02T12:01:00.000Z",
        last_event_seq: 2,
      }),
    ]));

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

  it("plays sound when an observed running session transitions to ended while hidden", async () => {
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
    const { rerender } = renderEffects([makeLiveSession({ status: "running" })]);

    rerender(effectsUi([
      makeLiveSession({
        status: "ended",
        ended_at: "2026-05-02T12:01:00.000Z",
        last_event_seq: 2,
      }),
    ]));

    await waitFor(() => expect(start).toHaveBeenCalledTimes(2));
    expect(stop).toHaveBeenCalledTimes(2);
  });
});
