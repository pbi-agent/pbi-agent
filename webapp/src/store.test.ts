import {
  getLiveSessionKey,
  getSavedSessionKey,
  useSessionStore,
} from "./store";
import type { LiveSession, WebEvent } from "./types";

function makeLiveSession(overrides: Partial<LiveSession> = {}): LiveSession {
  return {
    live_session_id: "live-1",
    session_id: "session-1",
    task_id: null,
    kind: "session",
    project_dir: "/workspace",
    created_at: "2026-04-16T12:00:00Z",
    status: "running",
    exit_code: null,
    fatal_error: null,
    ended_at: null,
    last_event_seq: 4,
    provider_id: "openai-main",
    profile_id: "analysis",
    provider: "OpenAI",
    model: "gpt-5.4",
    reasoning_effort: "high",
    ...overrides,
  };
}

describe("session store", () => {
  beforeEach(() => {
    useSessionStore.setState({
      activeSessionKey: null,
      sessionsByKey: {},
      liveSessionIndex: {},
      sessionIndex: {},
    });
  });

  it("moves live state onto the saved-session key when a session id is attached", () => {
    const liveKey = getLiveSessionKey("live-1");

    useSessionStore.getState().attachLiveSession(
      liveKey,
      makeLiveSession({ session_id: "session-9" }),
    );

    const state = useSessionStore.getState();
    const savedKey = getSavedSessionKey("session-9");
    expect(state.sessionsByKey[liveKey]).toBeUndefined();
    expect(state.liveSessionIndex["live-1"]).toBe(savedKey);
    expect(state.sessionIndex["session-9"]).toBe(savedKey);
    expect(state.sessionsByKey[savedKey]).toEqual(
      expect.objectContaining({
        liveSessionId: "live-1",
        sessionId: "session-9",
        lastEventSeq: 4,
      }),
    );
    expect(state.sessionsByKey[savedKey]?.runtime).toEqual(
      expect.objectContaining({
        provider: "OpenAI",
        model: "gpt-5.4",
        reasoning_effort: "high",
      }),
    );
  });

  it("ignores replayed websocket events and applies newer ones", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());

    const replayedEvent: WebEvent = {
      seq: 4,
      type: "message_added",
      created_at: "2026-04-16T12:00:01Z",
      payload: {
        item_id: "message-1",
        role: "assistant",
        content: "replayed",
      },
    };
    const freshEvent: WebEvent = {
      seq: 5,
      type: "message_added",
      created_at: "2026-04-16T12:00:02Z",
      payload: {
        item_id: "message-2",
        role: "assistant",
        content: "fresh",
      },
    };

    useSessionStore.getState().applyEvent(sessionKey, replayedEvent);
    useSessionStore.getState().applyEvent(sessionKey, freshEvent);

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.items).toHaveLength(1);
    expect(state.items[0]).toEqual(
      expect.objectContaining({
        kind: "message",
        itemId: "message-2",
        content: "fresh",
      }),
    );
    expect(state.itemsVersion).toBe(1);
    expect(state.lastEventSeq).toBe(5);
  });

  it("removes timeline items when a message_removed event arrives", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 5,
      type: "message_added",
      created_at: "2026-04-16T12:00:02Z",
      payload: {
        item_id: "user-1",
        role: "user",
        content: "remove me",
      },
    });
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 6,
      type: "message_removed",
      created_at: "2026-04-16T12:00:03Z",
      payload: { item_id: "user-1", restore_input: "remove me" },
    });

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.items).toHaveLength(0);
    expect(state.itemsVersion).toBe(2);
    expect(state.restoredInput).toBe("remove me");
  });

  it("ignores events from a stale live session after saved hydration", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());
    useSessionStore.getState().hydrateSavedSession("session-1", [
      {
        kind: "message",
        itemId: "history-1",
        role: "assistant",
        content: "stored",
        markdown: true,
      },
    ]);

    useSessionStore.getState().applyEvent(
      sessionKey,
      {
        seq: 5,
        type: "message_added",
        created_at: "2026-04-16T12:00:02Z",
        payload: {
          item_id: "message-1",
          role: "assistant",
          content: "stored",
        },
      },
      "live-1",
    );

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.items).toHaveLength(1);
    expect(state.items[0]).toEqual(
      expect.objectContaining({
        itemId: "history-1",
        content: "stored",
      }),
    );
  });

  it("captures turn usage updates with elapsed time", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());

    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 5,
      type: "usage_updated",
      created_at: "2026-04-16T12:00:03Z",
      payload: {
        scope: "turn",
        elapsed_seconds: 3.2,
        usage: {
          total_tokens: 42,
        },
      },
    });

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.turnUsage).toEqual({
      usage: { total_tokens: 42 },
      elapsedSeconds: 3.2,
    });
  });
});
