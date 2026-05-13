import {
  createEmptySessionState,
  getLiveSessionKey,
  getSavedSessionKey,
  reduceSessionEvent,
  resolveSessionEventTarget,
  type SessionRuntimeState,
  useSessionStore,
} from "./store";
import type {
  LiveSession,
  LiveSessionSnapshot,
  SessionWebEvent,
  UsagePayload,
  WebEvent,
} from "./types";

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
    compact_threshold: 200000,
    ...overrides,
  };
}

function makeEvent(overrides: {
  seq?: number;
  type?: SessionWebEvent["type"];
  created_at?: string;
  payload?: Record<string, unknown>;
} = {}): SessionWebEvent {
  return {
    seq: 1,
    type: "message_added",
    created_at: "2026-04-16T12:00:01Z",
    payload: {
      item_id: "message-1",
      role: "assistant",
      content: "hello",
    },
    ...overrides,
  } as SessionWebEvent;
}

function makeUsage(overrides: Partial<UsagePayload> = {}): UsagePayload {
  return {
    input_tokens: 0,
    cached_input_tokens: 0,
    cache_write_tokens: 0,
    cache_write_1h_tokens: 0,
    output_tokens: 0,
    reasoning_tokens: 0,
    provider_total_tokens: 0,
    sub_agent_input_tokens: 0,
    sub_agent_output_tokens: 0,
    sub_agent_reasoning_tokens: 0,
    sub_agent_provider_total_tokens: 0,
    sub_agent_cost_usd: 0,
    context_tokens: 0,
    total_tokens: 0,
    estimated_cost_usd: 0,
    main_agent_total_tokens: 0,
    sub_agent_total_tokens: 0,
    model: "gpt-5.4",
    service_tier: "default",
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

  it("resolves event targets by live id, saved session id, and fallback key", () => {
    const savedKey = getSavedSessionKey("session-1");
    const liveKey = getLiveSessionKey("live-2");
    const routingState = {
      sessionsByKey: {
        [liveKey]: { ...createEmptySessionState(), liveSessionId: "live-2" },
      },
      liveSessionIndex: { "live-1": savedKey },
      sessionIndex: { "session-1": savedKey },
    };

    expect(resolveSessionEventTarget(
      routingState,
      "fallback",
      makeEvent({ payload: { live_session_id: "live-1" } }),
    ).sessionKey).toBe(savedKey);
    expect(resolveSessionEventTarget(
      routingState,
      "fallback",
      makeEvent({ payload: { session_id: "session-1" } }),
    ).sessionKey).toBe(savedKey);
    expect(resolveSessionEventTarget(
      routingState,
      "fallback",
      makeEvent({ payload: {} }),
    ).sessionKey).toBe("fallback");
    expect(resolveSessionEventTarget(
      routingState,
      "fallback",
      makeEvent({ payload: { live_session_id: "live-2" } }),
    ).sessionKey).toBe(liveKey);
  });

  it("routes saved-session events from the wrong tab without mutating the fallback", () => {
    const sessionKey1 = getSavedSessionKey("session-1");
    const sessionKey2 = getSavedSessionKey("session-2");
    useSessionStore.getState().hydrateSavedSession("session-1", [], 0);
    useSessionStore.getState().hydrateSavedSession("session-2", [], 0);
    useSessionStore.getState().attachLiveSession(
      sessionKey2,
      makeLiveSession({ live_session_id: "live-2", session_id: "session-2", last_event_seq: 0 }),
    );

    const resolvedKey = useSessionStore.getState().applyEvent(sessionKey1, makeEvent({
      seq: 1,
      payload: {
        session_id: "session-2",
        live_session_id: "live-2",
        item_id: "message-2",
        role: "assistant",
        content: "routed",
      },
    }));

    const store = useSessionStore.getState();
    expect(resolvedKey.sessionKey).toBe(sessionKey2);
    expect(store.sessionsByKey[sessionKey1]?.items).toEqual([]);
    expect(store.sessionsByKey[sessionKey1]?.lastEventSeq).toBe(0);
    expect(store.sessionsByKey[sessionKey2]?.items).toEqual([
      expect.objectContaining({ itemId: "message-2", content: "routed" }),
    ]);
    expect(store.sessionIndex["session-2"]).toBe(sessionKey2);
    expect(store.liveSessionIndex["live-2"]).toBe(sessionKey2);
  });

  it("routes live-session events from the wrong tab by live id", () => {
    const liveKey1 = getLiveSessionKey("live-1");
    const liveKey2 = getLiveSessionKey("live-2");
    useSessionStore.getState().attachLiveSession(
      liveKey1,
      makeLiveSession({ live_session_id: "live-1", session_id: null, last_event_seq: 0 }),
    );
    useSessionStore.getState().attachLiveSession(
      liveKey2,
      makeLiveSession({ live_session_id: "live-2", session_id: null, last_event_seq: 0 }),
    );

    const resolvedKey = useSessionStore.getState().applyEvent(liveKey1, makeEvent({
      seq: 1,
      payload: {
        live_session_id: "live-2",
        item_id: "message-2",
        role: "assistant",
        content: "live routed",
      },
    }));

    const store = useSessionStore.getState();
    expect(resolvedKey.sessionKey).toBe(liveKey2);
    expect(store.sessionsByKey[liveKey1]?.items).toEqual([]);
    expect(store.sessionsByKey[liveKey2]?.items).toEqual([
      expect.objectContaining({ itemId: "message-2", content: "live routed" }),
    ]);
  });

  it("rejects an unknown saved target with an unattached live id without corrupting the fallback", () => {
    const fallbackKey = getLiveSessionKey("live-1");
    const targetKey = getSavedSessionKey("session-2");
    useSessionStore.getState().attachLiveSession(
      fallbackKey,
      makeLiveSession({ live_session_id: "live-1", session_id: null, last_event_seq: 0 }),
    );
    useSessionStore.getState().applyEvent(fallbackKey, makeEvent({
      seq: 1,
      payload: {
        live_session_id: "live-1",
        item_id: "fallback-message",
        role: "assistant",
        content: "fallback",
      },
    }));

    const resolvedKey = useSessionStore.getState().applyEvent(fallbackKey, makeEvent({
      seq: 1,
      payload: {
        session_id: "session-2",
        live_session_id: "live-2",
        item_id: "target-message",
        role: "assistant",
        content: "target",
      },
    }));

    const store = useSessionStore.getState();
    expect(resolvedKey.sessionKey).toBe(targetKey);
    expect(resolvedKey).toEqual(expect.objectContaining({
      applied: false,
      reason: "stale-live-session",
    }));
    expect(store.sessionsByKey[fallbackKey]?.items).toEqual([
      expect.objectContaining({ itemId: "fallback-message", content: "fallback" }),
    ]);
    expect(store.sessionsByKey[targetKey]).toBeUndefined();
    expect(store.liveSessionIndex["live-1"]).toBe(fallbackKey);
    expect(store.liveSessionIndex["live-2"]).toBeUndefined();
  });

  it("still rekeys a live fallback when session identity binds the same stream", () => {
    const liveKey = getLiveSessionKey("live-1");
    const savedKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      liveKey,
      makeLiveSession({ live_session_id: "live-1", session_id: null, last_event_seq: 0 }),
    );
    useSessionStore.getState().applyEvent(liveKey, makeEvent({
      seq: 1,
      payload: { live_session_id: "live-1", item_id: "message-1", content: "before bind" },
    }));

    const resolvedKey = useSessionStore.getState().applyEvent(liveKey, makeEvent({
      seq: 2,
      type: "session_identity",
      payload: { session_id: "session-1", live_session_id: "live-1" },
    }));

    const store = useSessionStore.getState();
    expect(resolvedKey.sessionKey).toBe(savedKey);
    expect(store.sessionsByKey[liveKey]).toBeUndefined();
    expect(store.sessionsByKey[savedKey]?.items).toEqual([
      expect.objectContaining({ itemId: "message-1", content: "before bind" }),
    ]);
    expect(store.liveSessionIndex["live-1"]).toBe(savedKey);
    expect(store.sessionIndex["session-1"]).toBe(savedKey);
  });

  it("routes late Kanban task events to the saved session without reattaching ended live ids", () => {
    const fallbackKey = getSavedSessionKey("session-other");
    const kanbanKey = getSavedSessionKey("session-kanban");
    useSessionStore.getState().hydrateSavedSession("session-other", [
      { kind: "message", itemId: "other-message", role: "assistant", content: "other", markdown: true },
    ], 0);
    useSessionStore.getState().hydrateSavedSession("session-kanban", [], 2);

    const resolvedKey = useSessionStore.getState().applyEvent(fallbackKey, makeEvent({
      seq: 3,
      type: "session_state",
      payload: {
        state: "ended",
        session_id: "session-kanban",
        live_session_id: "task-live-1",
        fatal_error: null,
      },
    }));

    const store = useSessionStore.getState();
    expect(resolvedKey.sessionKey).toBe(kanbanKey);
    expect(resolvedKey).toEqual(expect.objectContaining({
      applied: false,
      reason: "stale-live-session",
    }));
    expect(store.sessionsByKey[fallbackKey]?.items).toEqual([
      expect.objectContaining({ itemId: "other-message" }),
    ]);
    expect(store.sessionsByKey[kanbanKey]).toEqual(expect.objectContaining({
      liveSessionId: null,
      sessionEnded: false,
      lastEventSeq: 2,
    }));
    expect(store.liveSessionIndex["task-live-1"]).toBeUndefined();
  });

  it("rejects late saved-session events carrying a stale detached live id", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "old-live-1", session_id: "session-1", last_event_seq: 0 }),
    );
    useSessionStore.getState().hydrateSavedSession("session-1", [
      { kind: "message", itemId: "persisted-message", role: "assistant", content: "persisted", markdown: true },
    ], 0);

    const result = useSessionStore.getState().applyEvent(sessionKey, makeEvent({
      seq: 1,
      payload: {
        session_id: "session-1",
        live_session_id: "old-live-1",
        item_id: "late-message",
        role: "assistant",
        content: "late",
      },
    }));

    const store = useSessionStore.getState();
    expect(result).toEqual(expect.objectContaining({
      sessionKey,
      applied: false,
      reason: "stale-live-session",
    }));
    expect(store.sessionsByKey[sessionKey]).toEqual(expect.objectContaining({
      liveSessionId: null,
      lastEventSeq: 0,
    }));
    expect(store.sessionsByKey[sessionKey]?.items).toEqual([
      expect.objectContaining({ itemId: "persisted-message", content: "persisted" }),
    ]);
    expect(store.liveSessionIndex["old-live-1"]).toBeUndefined();
  });

  it("applies saved-session events for an explicitly attached new live stream", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().hydrateSavedSession("session-1", [], 0);
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "new-live-1", session_id: "session-1", last_event_seq: 0 }),
    );

    const result = useSessionStore.getState().applyEvent(sessionKey, makeEvent({
      seq: 1,
      payload: {
        session_id: "session-1",
        live_session_id: "new-live-1",
        item_id: "new-message",
        role: "assistant",
        content: "new",
      },
    }));

    const store = useSessionStore.getState();
    expect(result).toEqual(expect.objectContaining({ sessionKey, applied: true }));
    expect(store.sessionsByKey[sessionKey]).toEqual(expect.objectContaining({
      liveSessionId: "new-live-1",
      lastEventSeq: 1,
    }));
    expect(store.sessionsByKey[sessionKey]?.items).toEqual([
      expect.objectContaining({ itemId: "new-message", content: "new" }),
    ]);
    expect(store.liveSessionIndex["new-live-1"]).toBe(sessionKey);
  });

  it("reduces cursor decisions independently from the store", () => {
    const current = {
      ...createEmptySessionState("session-1"),
      liveSessionId: "live-1",
      lastEventSeq: 3,
    };

    expect(reduceSessionEvent(
      current,
      makeEvent({ seq: 3 }),
      { eventLiveSessionId: "live-1" },
    )).toEqual(expect.objectContaining({
      applied: false,
      reason: "duplicate-or-old",
    }));
    expect(reduceSessionEvent(
      current,
      makeEvent({ seq: 4 }),
      { eventLiveSessionId: "other-live" },
    )).toEqual(expect.objectContaining({
      applied: false,
      reason: "stale-live-session",
    }));
    const fresh = reduceSessionEvent(
      current,
      makeEvent({ seq: 4 }),
      { eventLiveSessionId: "live-1" },
    );
    expect(fresh.applied).toBe(true);
    expect(fresh.state.lastEventSeq).toBe(4);
  });

  it("requests reload instead of applying unrecoverable sequence gaps", () => {
    const current = {
      ...createEmptySessionState("session-1"),
      lastEventSeq: 3,
    };
    const reduced = reduceSessionEvent(current, makeEvent({ seq: 5 }));

    expect(reduced).toEqual(expect.objectContaining({
      applied: false,
      reason: "sequence-gap",
      reloadRequired: true,
    }));
    expect(reduced.state).toBe(current);

    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().hydrateSavedSession("session-1", [], 3);
    const applied = useSessionStore.getState().applyEvent(sessionKey, makeEvent({
      seq: 5,
      payload: { item_id: "message-gap", role: "assistant", content: "gap" },
    }));

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(applied).toEqual(expect.objectContaining({
      sessionKey,
      applied: false,
      reason: "sequence-gap",
      reloadRequired: true,
    }));
    expect(state.lastEventSeq).toBe(3);
    expect(state.items).toEqual([]);
  });

  it("applies transient message events without advancing the durable cursor", () => {
    const current = {
      ...createEmptySessionState("session-1"),
      liveSessionId: "live-1",
      lastEventSeq: 3,
    };

    const transient = reduceSessionEvent(
      current,
      makeEvent({
        seq: 0,
        payload: {
          item_id: "temp-reload-output",
          role: "assistant",
          content: "Reloaded workspace instructions.",
          markdown: true,
          transient: true,
        },
      }),
      { eventLiveSessionId: "live-1" },
    );

    expect(transient.applied).toBe(true);
    expect(transient.state.lastEventSeq).toBe(3);
    expect(transient.state.items).toEqual([
      expect.objectContaining({
        itemId: "temp-reload-output",
        content: "Reloaded workspace instructions.",
      }),
    ]);

    const nextDurable = reduceSessionEvent(
      transient.state,
      makeEvent({
        seq: 4,
        payload: { item_id: "durable-message", role: "assistant", content: "next" },
      }),
      { eventLiveSessionId: "live-1" },
    );
    expect(nextDurable.applied).toBe(true);
    expect(nextDurable.state.lastEventSeq).toBe(4);
  });

  it("reduces timeline mutations independently from routing", () => {
    const added = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      payload: {
        item_id: "message-1",
        role: "assistant",
        content: "draft",
      },
    }));
    const rekeyed = reduceSessionEvent(added.state, makeEvent({
      seq: 2,
      type: "message_rekeyed",
      payload: {
        old_item_id: "message-1",
        item: {
          item_id: "msg-1",
          role: "assistant",
          content: "draft",
          markdown: true,
        },
      },
    }));
    const removed = reduceSessionEvent(rekeyed.state, makeEvent({
      seq: 3,
      type: "message_removed",
      payload: { item_id: "msg-1", restore_input: "draft" },
    }));

    expect(added.state.items).toEqual([
      expect.objectContaining({ itemId: "message-1", content: "draft" }),
    ]);
    expect(rekeyed.state.items).toEqual([
      expect.objectContaining({ itemId: "msg-1", content: "draft" }),
    ]);
    expect(removed.state.items).toEqual([]);
    expect(removed.state.restoredInput).toBe("draft");
    expect(removed.state.itemsVersion).toBe(3);
  });

  it("preserves child identity when rekeying sub-agent messages", () => {
    const added = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      payload: {
        item_id: "subagent-1-message-1",
        role: "assistant",
        content: "child draft",
        sub_agent_id: "subagent-1",
      },
    }));
    const rekeyed = reduceSessionEvent(
      { ...added.state, restoredInput: "parent draft" },
      makeEvent({
        seq: 2,
        type: "message_rekeyed",
        payload: {
          old_item_id: "subagent-1-message-1",
          sub_agent_id: "subagent-1",
          item: {
            item_id: "msg-7",
            role: "assistant",
            content: "child draft",
            markdown: true,
          },
        },
      }),
    );

    expect(rekeyed.state.items).toEqual([
      expect.objectContaining({
        itemId: "msg-7",
        content: "child draft",
        subAgentId: "subagent-1",
      }),
    ]);
    expect(rekeyed.state.restoredInput).toBe("parent draft");
  });

  it("reduces runtime updates without mutating timeline items", () => {
    const current: SessionRuntimeState = {
      ...createEmptySessionState("session-1"),
      items: [{ kind: "thinking", itemId: "thinking-1", title: "Thinking", content: "body" }],
      itemsVersion: 1,
    };
    const input = reduceSessionEvent(current, makeEvent({
      seq: 1,
      type: "input_state",
      payload: { enabled: true },
    }));
    const waiting = reduceSessionEvent(input.state, makeEvent({
      seq: 2,
      type: "wait_state",
      payload: { active: true, message: "Waiting" },
    }));
    const processing = reduceSessionEvent(waiting.state, makeEvent({
      seq: 3,
      type: "processing_state",
      payload: { active: true, phase: "model_wait", message: "Thinking" },
    }));
    const runtime = reduceSessionEvent(processing.state, makeEvent({
      seq: 4,
      type: "session_runtime_updated",
      payload: {
        provider_id: "openai-main",
        profile_id: "review",
        provider: "OpenAI",
        model: "gpt-5.4",
        reasoning_effort: "medium",
        compact_threshold: 90000,
      },
    }));

    expect(runtime.state.inputEnabled).toBe(true);
    expect(runtime.state.waitMessage).toBe("Waiting");
    expect(runtime.state.processing).toEqual(expect.objectContaining({ phase: "model_wait" }));
    expect(runtime.state.runtime).toEqual(expect.objectContaining({ profile_id: "review" }));
    expect(runtime.state.items).toBe(current.items);
    expect(runtime.state.itemsVersion).toBe(1);
  });

  it("handles every session reducer event type deterministically", () => {
    const resetSource: SessionRuntimeState = {
      ...createEmptySessionState("session-1"),
      waitMessage: "Waiting",
      processing: { active: true, phase: "model_wait", message: "Thinking" },
      restoredInput: "restore me",
      turnUsage: { usage: null },
      sessionEnded: true,
      fatalError: "boom",
      pendingUserQuestions: { prompt_id: "prompt-1", questions: [] },
      subAgents: { subagent: { title: "Sub", status: "running" } },
      items: [{ kind: "thinking", itemId: "thinking-1", title: "Thinking", content: "body" }],
      itemsVersion: 1,
    };
    const reset = reduceSessionEvent(resetSource, makeEvent({
      seq: 1,
      type: "session_reset",
      payload: {},
    }));
    expect(reset.state).toEqual(expect.objectContaining({
      items: [],
      itemsVersion: 0,
      subAgents: {},
      waitMessage: null,
      processing: null,
      restoredInput: null,
      turnUsage: null,
      sessionEnded: false,
      fatalError: null,
      pendingUserQuestions: null,
      lastEventSeq: 1,
    }));

    const identity = reduceSessionEvent(createEmptySessionState(), makeEvent({
      seq: 1,
      type: "session_identity",
      payload: { session_id: "session-9" },
    }));
    expect(identity.state.sessionId).toBe("session-9");

    const input = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      type: "input_state",
      payload: { enabled: true },
    }));
    expect(input.state.inputEnabled).toBe(true);

    const waiting = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      type: "wait_state",
      payload: { active: true },
    }));
    const waitStopped = reduceSessionEvent(waiting.state, makeEvent({
      seq: 2,
      type: "wait_state",
      payload: { active: false },
    }));
    expect(waiting.state.waitMessage).toBe("Working...");
    expect(waitStopped.state.waitMessage).toBeNull();

    const processing = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      type: "processing_state",
      payload: {
        active: true,
        phase: "tool_execution",
        message: "Running tools",
        active_tool_count: 2,
      },
    }));
    const processingStopped = reduceSessionEvent(
      { ...processing.state, restoredInput: "restore me" },
      makeEvent({ seq: 2, type: "processing_state", payload: { active: false } }),
    );
    expect(processing.state.processing).toEqual(expect.objectContaining({
      phase: "tool_execution",
      active_tool_count: 2,
    }));
    expect(processingStopped.state.processing).toBeNull();
    expect(processingStopped.state.inputEnabled).toBe(true);

    const questions = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      type: "user_questions_requested",
      payload: {
        prompt_id: "prompt-1",
        questions: [
          {
            question_id: "question-1",
            question: "Which path?",
            suggestions: ["A", "B", "C"],
          },
        ],
      },
    }));
    const unresolved = reduceSessionEvent(questions.state, makeEvent({
      seq: 2,
      type: "user_questions_resolved",
      payload: { prompt_id: "other-prompt" },
    }));
    const resolved = reduceSessionEvent(unresolved.state, makeEvent({
      seq: 3,
      type: "user_questions_resolved",
      payload: { prompt_id: "prompt-1" },
    }));
    expect(questions.state.inputEnabled).toBe(false);
    expect(questions.state.pendingUserQuestions?.prompt_id).toBe("prompt-1");
    expect(unresolved.state.pendingUserQuestions?.prompt_id).toBe("prompt-1");
    expect(resolved.state.pendingUserQuestions).toBeNull();

    const sessionUsage = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      type: "usage_updated",
      payload: { scope: "session", usage: { total_tokens: 10 } },
    }));
    const turnUsage = reduceSessionEvent(sessionUsage.state, makeEvent({
      seq: 2,
      type: "usage_updated",
      payload: { scope: "turn", elapsed_seconds: 1.5, usage: { total_tokens: 3 } },
    }));
    const subAgentUsage = reduceSessionEvent(turnUsage.state, makeEvent({
      seq: 3,
      type: "usage_updated",
      payload: { scope: "session", sub_agent_id: "sub-1", usage: { total_tokens: 99 } },
    }));
    expect(sessionUsage.state.sessionUsage).toEqual({ total_tokens: 10 });
    expect(turnUsage.state.turnUsage).toEqual({
      usage: { total_tokens: 3 },
      elapsedSeconds: 1.5,
    });
    expect(subAgentUsage.state.sessionUsage).toEqual({ total_tokens: 10 });
    expect(subAgentUsage.state.subAgents["sub-1"]?.sessionUsage).toEqual({
      total_tokens: 99,
    });
    expect(subAgentUsage.state.lastEventSeq).toBe(3);

    const thinking = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      type: "thinking_updated",
      payload: { item_id: "thinking-1", title: "Reasoning", content: "body" },
    }));
    const toolGroup = reduceSessionEvent(thinking.state, makeEvent({
      seq: 2,
      type: "tool_group_added",
      payload: {
        item_id: "tool-group-1",
        label: "Shell",
        status: "completed",
        items: [{ text: "ok", metadata: { tool_name: "shell", success: true } }],
        sub_agent_id: "sub-1",
      },
    }));
    expect(thinking.state.items[0]).toEqual(expect.objectContaining({
      kind: "thinking",
      itemId: "thinking-1",
      title: "Reasoning",
    }));
    expect(toolGroup.state.items[1]).toEqual(expect.objectContaining({
      kind: "tool_group",
      itemId: "tool-group-1",
      subAgentId: "sub-1",
    }));

    const subAgent = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      type: "sub_agent_state",
      payload: { sub_agent_id: "sub-1", title: "Review", status: "completed" },
    }));
    expect(subAgent.state.subAgents["sub-1"]).toEqual({
      title: "Review",
      status: "completed",
    });

    const childWait = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      type: "wait_state",
      payload: {
        active: true,
        message: "Child model wait",
        sub_agent_id: "sub-1",
      },
    }));
    const childProcessing = reduceSessionEvent(childWait.state, makeEvent({
      seq: 2,
      type: "processing_state",
      payload: {
        active: true,
        phase: "model_wait",
        message: "Child model wait",
        sub_agent_id: "sub-1",
      },
    }));
    const childCompleted = reduceSessionEvent(childProcessing.state, makeEvent({
      seq: 3,
      type: "sub_agent_state",
      payload: { sub_agent_id: "sub-1", title: "Review", status: "completed" },
    }));
    expect(childWait.state.waitMessage).toBeNull();
    expect(childWait.state.subAgents["sub-1"]?.waitMessage).toBe("Child model wait");
    expect(childProcessing.state.processing).toBeNull();
    expect(childProcessing.state.subAgents["sub-1"]?.processing).toEqual({
      active: true,
      phase: "model_wait",
      message: "Child model wait",
    });
    expect(childCompleted.state.subAgents["sub-1"]).toEqual({
      title: "Review",
      status: "completed",
    });

    const endedLive = reduceSessionEvent(createEmptySessionState(), makeEvent({
      seq: 1,
      type: "session_state",
      payload: { state: "ended", fatal_error: "boom" },
    }));
    const endedSaved = reduceSessionEvent(
      { ...createEmptySessionState("session-1"), liveSessionId: "live-1" },
      makeEvent({
        seq: 1,
        type: "session_state",
        payload: { state: "ended", session_id: "session-1", fatal_error: null },
      }),
    );
    const running = reduceSessionEvent(
      { ...createEmptySessionState("session-1"), sessionEnded: true, fatalError: "boom" },
      makeEvent({ seq: 1, type: "session_state", payload: { state: "running" } }),
    );
    expect(endedLive.state.sessionEnded).toBe(true);
    expect(endedLive.state.fatalError).toBe("boom");
    expect(endedSaved.state.liveSessionId).toBeNull();
    expect(endedSaved.state.sessionEnded).toBe(false);
    expect(running.state.sessionEnded).toBe(false);
    expect(running.state.fatalError).toBeNull();

    const runtime = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      type: "session_runtime_updated",
      payload: {
        provider_id: "openai-main",
        profile_id: "review",
        provider: "OpenAI",
        model: "gpt-5.4",
        reasoning_effort: "medium",
        compact_threshold: 90000,
      },
    }));
    const nextRuntime = reduceSessionEvent(runtime.state, makeEvent({
      seq: 2,
      type: "session_runtime_updated",
      payload: {
        provider_id: "openai-main",
        profile_id: "analysis",
        provider: "OpenAI",
        model: "gpt-5.4-mini",
        reasoning_effort: "low",
        compact_threshold: 45000,
      },
    }));
    expect(runtime.state.runtime).toEqual(expect.objectContaining({
      profile_id: "review",
      compact_threshold: 90000,
    }));
    expect(nextRuntime.state.runtime).toEqual(expect.objectContaining({
      profile_id: "analysis",
      compact_threshold: 45000,
    }));
    expect(nextRuntime.state.lastEventSeq).toBe(2);
  });

  it("ignores duplicate and out-of-order reducer events deterministically", () => {
    const current = {
      ...createEmptySessionState("session-1"),
      lastEventSeq: 4,
    };
    const fresh = reduceSessionEvent(current, makeEvent({
      seq: 5,
      payload: { item_id: "message-1", role: "assistant", content: "fresh" },
    }));
    const older = reduceSessionEvent(fresh.state, makeEvent({
      seq: 4,
      payload: { item_id: "message-older", role: "assistant", content: "older" },
    }));
    const duplicate = reduceSessionEvent(fresh.state, makeEvent({
      seq: 5,
      payload: { item_id: "message-1", role: "assistant", content: "fresh" },
    }));
    const adopted = reduceSessionEvent(createEmptySessionState("session-1"), makeEvent({
      seq: 1,
      payload: { item_id: "message-2", role: "assistant", content: "adopt" },
    }), { eventLiveSessionId: "live-1" });

    expect(older).toEqual(expect.objectContaining({
      applied: false,
      reason: "duplicate-or-old",
    }));
    expect(older.state).toBe(fresh.state);
    expect(duplicate).toEqual(expect.objectContaining({
      applied: false,
      reason: "duplicate-or-old",
    }));
    expect(adopted.state.liveSessionId).toBe("live-1");

    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());
    useSessionStore.getState().applyEvent(sessionKey, makeEvent({
      seq: 5,
      payload: { item_id: "message-1", role: "assistant", content: "fresh" },
    }));
    useSessionStore.getState().applyEvent(sessionKey, makeEvent({
      seq: 5,
      payload: { item_id: "message-1", role: "assistant", content: "fresh" },
    }));

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.items).toHaveLength(1);
    expect(state.itemsVersion).toBe(1);
    expect(state.lastEventSeq).toBe(5);
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

  it("rekeys optimistic messages to persisted message ids", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 5,
      type: "message_added",
      created_at: "2026-04-16T12:00:02Z",
      payload: {
        item_id: "user-optimistic",
        role: "user",
        content: "hello",
      },
    });

    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 6,
      type: "message_rekeyed",
      created_at: "2026-04-16T12:00:03Z",
      payload: {
        old_item_id: "user-optimistic",
        item: {
          item_id: "msg-10",
          message_id: "msg-10",
          part_ids: {
            content: "msg-10:content",
            file_paths: [],
            image_attachments: [],
          },
          role: "user",
          content: "hello",
          markdown: false,
        },
      },
    });

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.items).toHaveLength(1);
    expect(state.items[0]).toEqual(
      expect.objectContaining({
        itemId: "msg-10",
        messageId: "msg-10",
        partIds: {
          content: "msg-10:content",
          file_paths: [],
          image_attachments: [],
        },
      }),
    );
    expect(state.itemsVersion).toBe(2);
  });

  it("clears stale live and ask-user state when hydrating a saved session", () => {
    const sessionKey = getSavedSessionKey("session-1");
    const otherSessionKey = getSavedSessionKey("session-2");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());
    useSessionStore.getState().setConnection(sessionKey, "connected");
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 5,
      type: "wait_state",
      created_at: "2026-04-16T12:00:02Z",
      payload: { active: true, message: "Waiting" },
    });
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 6,
      type: "processing_state",
      created_at: "2026-04-16T12:00:03Z",
      payload: { active: true, phase: "model_wait", message: "Thinking" },
    });
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 7,
      type: "user_questions_requested",
      created_at: "2026-04-16T12:00:04Z",
      payload: {
        prompt_id: "prompt-1",
        questions: [
          {
            question_id: "question-1",
            question: "Which path?",
            suggestions: ["A", "B", "C"],
          },
        ],
      },
    });
    useSessionStore.getState().attachLiveSession(
      otherSessionKey,
      makeLiveSession({ live_session_id: "live-2", session_id: "session-2", last_event_seq: 5 }),
    );
    useSessionStore.getState().hydrateSavedSession(
      "session-1",
      [
        {
          kind: "message",
          itemId: "history-1",
          role: "assistant",
          content: "stored",
          markdown: true,
        },
      ],
      7,
    );

    let store = useSessionStore.getState();
    expect(store.liveSessionIndex["live-1"]).toBeUndefined();
    expect(store.sessionsByKey[sessionKey]?.liveSessionId).toBeNull();
    expect(store.sessionsByKey[sessionKey]).toEqual(expect.objectContaining({
      connection: "disconnected",
      inputEnabled: false,
      waitMessage: null,
      processing: null,
      pendingUserQuestions: null,
    }));

    const result = useSessionStore.getState().applyEvent(otherSessionKey, {
      seq: 8,
      type: "message_added",
      created_at: "2026-04-16T12:00:05Z",
      payload: {
        live_session_id: "live-1",
        item_id: "message-1",
        role: "assistant",
        content: "stale live event",
      },
    });

    store = useSessionStore.getState();
    const state = store.sessionsByKey[sessionKey];
    expect(result.sessionKey).toBe(otherSessionKey);
    expect(result).toEqual(expect.objectContaining({
      applied: false,
      reason: "stale-live-session",
    }));
    expect(state.items).toHaveLength(1);
    expect(state.items[0]).toEqual(
      expect.objectContaining({
        itemId: "history-1",
        content: "stored",
      }),
    );
    expect(state.liveSessionId).toBeNull();
    expect(store.liveSessionIndex["live-1"]).toBeUndefined();
    expect(store.liveSessionIndex["live-2"]).toBe(otherSessionKey);

    const sameFallbackResult = useSessionStore.getState().applyEvent(sessionKey, {
      seq: 8,
      type: "message_added",
      created_at: "2026-04-16T12:00:06Z",
      payload: {
        live_session_id: "live-1",
        item_id: "message-2",
        role: "assistant",
        content: "late stale live event",
      },
    });

    store = useSessionStore.getState();
    expect(sameFallbackResult).toEqual(expect.objectContaining({
      sessionKey,
      applied: false,
      reason: "stale-live-session",
    }));
    expect(store.sessionsByKey[sessionKey]?.liveSessionId).toBeNull();
    expect(store.sessionsByKey[sessionKey]?.items).toHaveLength(1);
  });

  it("detaches a finished live run from a saved session so chat can continue", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());

    useSessionStore.getState().applyEvent(
      sessionKey,
      {
        seq: 5,
        type: "session_state",
        created_at: "2026-04-16T12:00:03Z",
        payload: {
          state: "ended",
          session_id: "session-1",
          live_session_id: "live-1",
          exit_code: 0,
          fatal_error: null,
        },
      },
      "live-1",
    );

    const store = useSessionStore.getState();
    const state = store.sessionsByKey[sessionKey];
    expect(state.liveSessionId).toBeNull();
    expect(state.sessionEnded).toBe(false);
    expect(state.inputEnabled).toBe(false);
    expect(store.liveSessionIndex["live-1"]).toBeUndefined();
    expect(store.sessionIndex["session-1"]).toBe(sessionKey);
  });

  it("resets the event cursor when a saved session starts a new live run", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "old-live", last_event_seq: 46 }),
    );
    useSessionStore.getState().applyEvent(
      sessionKey,
      {
        seq: 46,
        type: "session_state",
        created_at: "2026-04-16T12:00:03Z",
        payload: {
          state: "ended",
          session_id: "session-1",
          live_session_id: "old-live",
          exit_code: 0,
          fatal_error: null,
        },
      },
      "old-live",
    );

    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "new-live", last_event_seq: 5 }),
      { preserveItems: true, preserveEventCursor: true },
    );

    const store = useSessionStore.getState();
    expect(store.sessionsByKey[sessionKey]?.lastEventSeq).toBe(0);
    expect(store.liveSessionIndex["new-live"]).toBe(sessionKey);
  });

  it("does not let a stale submit response disable input after newer stream events", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "live-1", last_event_seq: 8 }),
    );
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 9,
      type: "input_state",
      created_at: "2026-04-16T12:00:03Z",
      payload: {
        enabled: false,
        session_id: "session-1",
        live_session_id: "live-1",
      },
    });
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 10,
      type: "input_state",
      created_at: "2026-04-16T12:00:04Z",
      payload: {
        enabled: true,
        session_id: "session-1",
        live_session_id: "live-1",
      },
    });

    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "live-1", last_event_seq: 9 }),
      { preserveItems: true, preserveEventCursor: true },
    );

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.lastEventSeq).toBe(10);
    expect(state.inputEnabled).toBe(true);
    expect(state.liveSessionId).toBe("live-1");
  });

  it("does not disable input when a submit response matches the applied stream cursor", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "live-1", last_event_seq: 8 }),
    );
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 9,
      type: "input_state",
      created_at: "2026-04-16T12:00:03Z",
      payload: {
        enabled: true,
        session_id: "session-1",
        live_session_id: "live-1",
      },
    });

    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ live_session_id: "live-1", last_event_seq: 9 }),
      { preserveItems: true, preserveEventCursor: true },
    );

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.lastEventSeq).toBe(9);
    expect(state.inputEnabled).toBe(true);
  });

  it("resets stream state so a snapshot can replace an incomplete replay", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 5,
      type: "message_added",
      created_at: "2026-04-16T12:00:02Z",
      payload: {
        item_id: "message-1",
        role: "assistant",
        content: "partial",
      },
    });

    useSessionStore.getState().resetStreamState(sessionKey);

    const store = useSessionStore.getState();
    expect(store.sessionsByKey[sessionKey]).toEqual(expect.objectContaining({
      sessionId: "session-1",
      liveSessionId: null,
      lastEventSeq: 0,
      items: [],
      connection: "disconnected",
    }));
    expect(store.liveSessionIndex["live-1"]).toBeUndefined();
    expect(store.sessionIndex["session-1"]).toBe(sessionKey);
  });

  it("can reset stream state while preserving the active live session identity", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 5,
      type: "message_added",
      created_at: "2026-04-16T12:00:02Z",
      payload: {
        item_id: "message-1",
        role: "assistant",
        content: "partial",
      },
    });

    useSessionStore.getState().resetStreamState(sessionKey, { preserveLiveSession: true });

    const store = useSessionStore.getState();
    expect(store.sessionsByKey[sessionKey]).toEqual(expect.objectContaining({
      sessionId: "session-1",
      liveSessionId: "live-1",
      lastEventSeq: 0,
      items: [],
      connection: "disconnected",
    }));
    expect(store.liveSessionIndex["live-1"]).toBe(sessionKey);
    expect(store.sessionIndex["session-1"]).toBe(sessionKey);
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
        usage: makeUsage({ total_tokens: 42 }),
      },
    });

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.turnUsage).toEqual({
      usage: makeUsage({ total_tokens: 42 }),
      elapsedSeconds: 3.2,
    });
  });

  it("captures top-level session usage updates for live context progress", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());

    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 5,
      type: "usage_updated",
      created_at: "2026-04-16T12:00:03Z",
      payload: {
        scope: "session",
        usage: makeUsage({
          context_tokens: 120000,
          total_tokens: 42,
        }),
      },
    });

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.sessionUsage).toEqual(makeUsage({
      context_tokens: 120000,
      total_tokens: 42,
    }));
  });

  it("hydrates sub-agent usage from live snapshots", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().hydrateLiveSnapshot(
      sessionKey,
      makeLiveSession(),
      {
        live_session_id: "live-1",
        session_id: "session-1",
        runtime: null,
        input_enabled: false,
        wait_message: null,
        processing: null,
        session_usage: makeUsage({ context_tokens: 120000 }),
        turn_usage: null,
        session_ended: false,
        fatal_error: null,
        pending_user_questions: null,
        items: [],
        sub_agents: {
          "subagent-1": {
            title: "Researcher",
            status: "completed",
            session_usage: makeUsage({ context_tokens: 5000 }),
            turn_usage: {
              usage: makeUsage({ context_tokens: 4200 }),
              elapsed_seconds: 2.5,
            },
          },
        },
        last_event_seq: 7,
      } satisfies LiveSessionSnapshot,
    );

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.sessionUsage).toEqual(makeUsage({ context_tokens: 120000 }));
    expect(state.subAgents["subagent-1"]).toEqual({
      title: "Researcher",
      status: "completed",
      sessionUsage: makeUsage({ context_tokens: 5000 }),
      turnUsage: {
        usage: makeUsage({ context_tokens: 4200 }),
        elapsedSeconds: 2.5,
      },
    });
  });

  it("stores sub-agent usage updates separately from the top-level context gauge", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(sessionKey, makeLiveSession());

    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 5,
      type: "usage_updated",
      created_at: "2026-04-16T12:00:03Z",
      payload: {
        scope: "session",
        usage: makeUsage({ context_tokens: 120000 }),
      },
    });
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 6,
      type: "usage_updated",
      created_at: "2026-04-16T12:00:04Z",
      payload: {
        scope: "session",
        sub_agent_id: "subagent-1",
        usage: makeUsage({ context_tokens: 5000 }),
      },
    });
    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 7,
      type: "usage_updated",
      created_at: "2026-04-16T12:00:05Z",
      payload: {
        scope: "turn",
        elapsed_seconds: 1.8,
        sub_agent_id: "subagent-1",
        usage: makeUsage({ context_tokens: 4200 }),
      },
    });

    const state = useSessionStore.getState().sessionsByKey[sessionKey];
    expect(state.sessionUsage).toEqual(makeUsage({ context_tokens: 120000 }));
    expect(state.subAgents["subagent-1"]?.sessionUsage).toEqual(
      makeUsage({ context_tokens: 5000 }),
    );
    expect(state.subAgents["subagent-1"]?.turnUsage).toEqual({
      usage: makeUsage({ context_tokens: 4200 }),
      elapsedSeconds: 1.8,
    });
  });

  it("stores compact threshold from live sessions and runtime updates", () => {
    const sessionKey = getSavedSessionKey("session-1");
    useSessionStore.getState().attachLiveSession(
      sessionKey,
      makeLiveSession({ compact_threshold: 150000 }),
    );

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.runtime)
      .toEqual(expect.objectContaining({ compact_threshold: 150000 }));

    useSessionStore.getState().applyEvent(sessionKey, {
      seq: 5,
      type: "session_runtime_updated",
      created_at: "2026-04-16T12:00:03Z",
      payload: {
        provider_id: "openai-main",
        profile_id: "review",
        provider: "OpenAI",
        model: "gpt-5.4",
        reasoning_effort: "medium",
        compact_threshold: 90000,
      },
    });

    expect(useSessionStore.getState().sessionsByKey[sessionKey]?.runtime)
      .toEqual(expect.objectContaining({
        profile_id: "review",
        compact_threshold: 90000,
      }));
  });
});
