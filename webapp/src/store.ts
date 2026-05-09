import { create } from "zustand";

import type {
  ImageAttachment,
  LiveSession,
  LiveSessionRuntime,
  LiveSessionSnapshot,
  MessagePartIds,
  PendingUserQuestions,
  ProcessingPhase,
  ProcessingState,
  SessionWebEvent,
  TimelineItem,
  TimelineToolGroupEntry,
  ToolCallMetadata,
  ToolCallStatus,
  ToolGroupStatus,
  UsagePayload,
  WebEvent,
} from "./types";

export type ConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "recovering"
  | "recovered"
  | "recovery_failed";

export type SubAgentState = {
  title: string;
  status: string;
};

export type SessionRuntimeState = {
  liveSessionId: string | null;
  sessionId: string | null;
  runtime: LiveSessionRuntime | null;
  connection: ConnectionState;
  inputEnabled: boolean;
  waitMessage: string | null;
  processing: ProcessingState | null;
  restoredInput: string | null;
  sessionUsage: UsagePayload | null;
  turnUsage: { usage: UsagePayload | null; elapsedSeconds?: number } | null;
  sessionEnded: boolean;
  fatalError: string | null;
  pendingUserQuestions: PendingUserQuestions | null;
  items: TimelineItem[];
  itemsVersion: number;
  subAgents: Record<string, SubAgentState>;
  lastEventSeq: number;
};

type SessionStore = {
  activeSessionKey: string | null;
  sessionsByKey: Record<string, SessionRuntimeState>;
  liveSessionIndex: Record<string, string>;
  sessionIndex: Record<string, string>;
  setActiveSession: (sessionKey: string | null) => void;
  hydrateSavedSession: (sessionId: string, items?: TimelineItem[], lastEventSeq?: number) => void;
  attachLiveSession: (
    sessionKey: string,
    session: LiveSession,
    options?: { preserveItems?: boolean; preserveEventCursor?: boolean },
  ) => string;
  hydrateLiveSnapshot: (
    sessionKey: string,
    session: LiveSession,
    snapshot: LiveSessionSnapshot,
  ) => string;
  updateRuntimeFromSession: (sessionKey: string, session: LiveSession) => void;
  setConnection: (sessionKey: string, connection: ConnectionState) => void;
  resetStreamState: (sessionKey: string, options?: {
    preserveItems?: boolean;
    preserveLiveSession?: boolean;
  }) => void;
  applyEvent: (
    sessionKey: string,
    event: WebEvent,
    liveSessionId?: string | null,
  ) => ApplySessionEventResult;
  consumeRestoredInput: (sessionKey: string) => void;
};

export function createEmptySessionState(sessionId: string | null = null): SessionRuntimeState {
  return {
    liveSessionId: null,
    sessionId,
    runtime: null,
    connection: "disconnected",
    inputEnabled: false,
    waitMessage: null,
    processing: null,
    restoredInput: null,
    sessionUsage: null,
    turnUsage: null,
    sessionEnded: false,
    fatalError: null,
    pendingUserQuestions: null,
    items: [],
    itemsVersion: 0,
    subAgents: {},
    lastEventSeq: 0,
  };
}

export function getSavedSessionKey(sessionId: string): string {
  return `session:${sessionId}`;
}

export function getLiveSessionKey(liveSessionId: string): string {
  return `live:${liveSessionId}`;
}

function runtimeFromSession(session: LiveSession): LiveSessionRuntime {
  return {
    provider_id: session.provider_id,
    profile_id: session.profile_id,
    provider: session.provider,
    model: session.model,
    reasoning_effort: session.reasoning_effort,
    compact_threshold: session.compact_threshold,
  };
}

function upsertItem(items: TimelineItem[], nextItem: TimelineItem): TimelineItem[] {
  const index = items.findIndex((item) => item.itemId === nextItem.itemId);
  if (index === -1) {
    return [...items, nextItem];
  }
  const updated = [...items];
  updated[index] = nextItem;
  return updated;
}

function rekeyItem(
  items: TimelineItem[],
  oldItemId: string,
  nextItem: TimelineItem,
): TimelineItem[] {
  const withoutOld = oldItemId && oldItemId !== nextItem.itemId
    ? items.filter((item) => item.itemId !== oldItemId)
    : items;
  return upsertItem(withoutOld, nextItem);
}

function readString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function readPendingUserQuestions(value: unknown): PendingUserQuestions | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const promptId = readString(record.prompt_id);
  if (!promptId || !Array.isArray(record.questions)) return null;
  const questions = record.questions.flatMap((rawQuestion) => {
    if (!rawQuestion || typeof rawQuestion !== "object") return [];
    const questionRecord = rawQuestion as Record<string, unknown>;
    const suggestions = Array.isArray(questionRecord.suggestions)
      ? questionRecord.suggestions.filter((suggestion): suggestion is string => typeof suggestion === "string")
      : [];
    if (suggestions.length !== 3) return [];
    const questionId = readString(questionRecord.question_id);
    const question = readString(questionRecord.question);
    if (!questionId || !question) return [];
    return [{
      question_id: questionId,
      question,
      suggestions: [suggestions[0], suggestions[1], suggestions[2]] as [string, string, string],
      recommended_suggestion_index: 0 as const,
    }];
  });
  return questions.length > 0 ? { prompt_id: promptId, questions } : null;
}

function readOptionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function readStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function readMessagePartIds(value: unknown): MessagePartIds | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const content = readString(record.content);
  if (!content) return undefined;
  return {
    content,
    file_paths: readStringList(record.file_paths),
    image_attachments: readStringList(record.image_attachments),
  };
}

function readTimelineRole(
  value: unknown,
): "user" | "assistant" | "notice" | "error" | "debug" {
  switch (value) {
    case "user":
    case "assistant":
    case "notice":
    case "error":
    case "debug":
      return value;
    default:
      return "assistant";
  }
}

function readProcessingPhase(value: unknown): ProcessingPhase | null {
  switch (value) {
    case "starting":
    case "model_wait":
    case "tool_execution":
    case "finalizing":
    case "interrupting":
    case "retry_wait":
      return value;
    default:
      return null;
  }
}

function readToolCallStatus(value: unknown): ToolCallStatus | undefined {
  switch (value) {
    case "running":
    case "completed":
    case "failed":
      return value;
    default:
      return undefined;
  }
}

function readToolGroupStatus(value: unknown): ToolGroupStatus | undefined {
  switch (value) {
    case "running":
    case "completed":
      return value;
    default:
      return undefined;
  }
}

function isImageAttachment(value: unknown): value is ImageAttachment {
  if (value === null || typeof value !== "object") {
    return false;
  }
  return "upload_id" in value
    && typeof (value as { upload_id: unknown }).upload_id === "string";
}

function readBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function readLineNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0
    ? value
    : null;
}

function readDiffLineNumbers(
  value: unknown,
): Array<{ old: number | null; new: number | null }> | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value.map((item) => {
    if (item === null || typeof item !== "object") {
      return { old: null, new: null };
    }
    const record = item as Record<string, unknown>;
    return {
      old: readLineNumber(record.old),
      new: readLineNumber(record.new),
    };
  });
}

function readToolCallMetadata(value: unknown): ToolCallMetadata | undefined {
  if (value === null || typeof value !== "object") {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  return {
    ...record,
    tool_name: readOptionalString(record.tool_name),
    path: readOptionalString(record.path),
    operation: readOptionalString(record.operation),
    success: readBoolean(record.success),
    detail: readOptionalString(record.detail),
    diff: readOptionalString(record.diff),
    diff_line_numbers: readDiffLineNumbers(record.diff_line_numbers),
    call_id: readOptionalString(record.call_id),
    status: readToolCallStatus(record.status),
    command: readOptionalString(record.command),
    working_directory: readOptionalString(record.working_directory),
    timeout_ms:
      typeof record.timeout_ms === "number" || typeof record.timeout_ms === "string"
        ? record.timeout_ms
        : undefined,
    exit_code:
      typeof record.exit_code === "number" || record.exit_code === null
        ? record.exit_code
        : undefined,
    timed_out: readBoolean(record.timed_out),
  };
}

function readProcessingState(value: unknown): ProcessingState | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const active = Boolean(record.active);
  if (!active) return null;
  return {
    active,
    phase: readProcessingPhase(record.phase),
    message: typeof record.message === "string" ? record.message : null,
    active_tool_count:
      typeof record.active_tool_count === "number" ? record.active_tool_count : undefined,
  };
}

function readToolGroupItems(value: unknown): TimelineToolGroupEntry[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => {
    if (item === null || typeof item !== "object") {
      return { text: String(item ?? "") };
    }
    const record = item as Record<string, unknown>;
    return {
      text: readString(record.text),
      classes: readOptionalString(record.classes),
      metadata: readToolCallMetadata(record.metadata),
    };
  });
}

function mapSnapshotItem(raw: Record<string, unknown>): TimelineItem | null {
  const kind = raw.kind;
  const itemId = typeof raw.itemId === "string"
    ? raw.itemId
    : typeof raw.item_id === "string"
      ? raw.item_id
      : null;
  if (!itemId || typeof kind !== "string") return null;
  if (kind === "message") {
    return {
      kind: "message",
      itemId,
      messageId: readOptionalString(raw.message_id),
      partIds: readMessagePartIds(raw.part_ids),
      role: readTimelineRole(raw.role),
      content: readString(raw.content),
      filePaths: Array.isArray(raw.file_paths)
        ? raw.file_paths.filter((value): value is string => typeof value === "string")
        : undefined,
      imageAttachments: Array.isArray(raw.image_attachments)
        ? raw.image_attachments.filter(isImageAttachment)
        : undefined,
      markdown: Boolean(raw.markdown),
      subAgentId: readOptionalString(raw.sub_agent_id),
    };
  }
  if (kind === "thinking") {
    return {
      kind: "thinking",
      itemId,
      title: readString(raw.title, "Thinking"),
      content: readString(raw.content),
      subAgentId: readOptionalString(raw.sub_agent_id),
    };
  }
  if (kind === "tool_group") {
    return {
      kind: "tool_group",
      itemId,
      label: readString(raw.label, "Tool calls"),
      status: readToolGroupStatus(raw.status),
      items: readToolGroupItems(raw.items),
      subAgentId: readOptionalString(raw.sub_agent_id),
    };
  }
  return null;
}

function moveSessionState(
  state: SessionStore,
  fromKey: string,
  toKey: string,
): SessionStore {
  if (fromKey === toKey || !(fromKey in state.sessionsByKey)) {
    return state;
  }
  const sessionState = state.sessionsByKey[fromKey];
  const nextSessionsByKey = { ...state.sessionsByKey };
  delete nextSessionsByKey[fromKey];
  nextSessionsByKey[toKey] = sessionState;

  const nextLiveSessionIndex = Object.fromEntries(
    Object.entries(state.liveSessionIndex).map(([id, key]) => [id, key === fromKey ? toKey : key]),
  );
  const nextSessionIndex = Object.fromEntries(
    Object.entries(state.sessionIndex).map(([id, key]) => [id, key === fromKey ? toKey : key]),
  );

  return {
    ...state,
    sessionsByKey: nextSessionsByKey,
    liveSessionIndex: nextLiveSessionIndex,
    sessionIndex: nextSessionIndex,
    activeSessionKey: state.activeSessionKey === fromKey ? toKey : state.activeSessionKey,
  };
}

export type SessionEventRoutingState = Pick<
  SessionStore,
  "sessionsByKey" | "liveSessionIndex" | "sessionIndex"
>;

export type SessionEventTarget = {
  sessionKey: string;
  liveSessionId: string | null;
  sessionId: string | null;
};

export type ReduceSessionEventResult = {
  state: SessionRuntimeState;
  applied: boolean;
  reason?: "stale-live-session" | "duplicate-or-old" | "sequence-gap";
  reloadRequired?: true;
};

export type ApplySessionEventResult = {
  sessionKey: string;
  applied: boolean;
  reason?: ReduceSessionEventResult["reason"];
  reloadRequired?: true;
};

function eventSessionId(event: WebEvent): string | null {
  return "session_id" in event.payload && typeof event.payload.session_id === "string"
    ? event.payload.session_id
    : null;
}

function eventLiveSessionId(event: WebEvent): string | null {
  return "live_session_id" in event.payload && typeof event.payload.live_session_id === "string"
    ? event.payload.live_session_id
    : null;
}

function findSessionKeyByLiveSessionId(
  sessionsByKey: Record<string, SessionRuntimeState>,
  liveSessionId: string,
): string | null {
  return Object.entries(sessionsByKey).find(([, session]) => (
    session.liveSessionId === liveSessionId
  ))?.[0] ?? null;
}

export function resolveSessionEventTarget(
  state: SessionEventRoutingState,
  fallbackSessionKey: string,
  event: WebEvent,
  fallbackLiveSessionId: string | null = null,
): SessionEventTarget {
  const sessionId = eventSessionId(event);
  const liveSessionId = eventLiveSessionId(event) ?? fallbackLiveSessionId;
  if (sessionId) {
    return {
      sessionKey: state.sessionIndex[sessionId] ?? getSavedSessionKey(sessionId),
      liveSessionId,
      sessionId,
    };
  }
  if (liveSessionId) {
    return {
      sessionKey: state.liveSessionIndex[liveSessionId]
        ?? findSessionKeyByLiveSessionId(state.sessionsByKey, liveSessionId)
        ?? fallbackSessionKey,
      liveSessionId,
      sessionId: null,
    };
  }
  return { sessionKey: fallbackSessionKey, liveSessionId: null, sessionId: null };
}

export function reduceSessionEvent(
  current: SessionRuntimeState,
  event: SessionWebEvent,
  options: {
    eventLiveSessionId?: string | null;
    allowLiveSessionAdoption?: boolean;
  } = {},
): ReduceSessionEventResult {
  const nextSessionId = eventSessionId(event);
  const eventLiveId = options.eventLiveSessionId ?? eventLiveSessionId(event);
  const transient = event.type === "message_added"
    && (event.payload as Record<string, unknown>).transient === true;
  if (eventLiveId && current.liveSessionId && current.liveSessionId !== eventLiveId) {
    return { state: current, applied: false, reason: "stale-live-session" };
  }
  if (
    eventLiveId
    && !current.liveSessionId
    && options.allowLiveSessionAdoption === false
  ) {
    return { state: current, applied: false, reason: "stale-live-session" };
  }
  if (!transient && event.seq <= current.lastEventSeq) {
    return { state: current, applied: false, reason: "duplicate-or-old" };
  }
  if (!transient && event.seq > current.lastEventSeq + 1) {
    return {
      state: current,
      applied: false,
      reason: "sequence-gap",
      reloadRequired: true,
    };
  }

  const patch: Partial<SessionRuntimeState> = transient ? {} : { lastEventSeq: event.seq };
  if (eventLiveId && !current.liveSessionId) {
    patch.liveSessionId = eventLiveId;
  }

  switch (event.type) {
    case "session_reset":
      patch.items = [];
      patch.itemsVersion = 0;
      patch.subAgents = {};
      patch.waitMessage = null;
      patch.processing = null;
      patch.restoredInput = null;
      patch.turnUsage = null;
      patch.sessionEnded = false;
      patch.fatalError = null;
      patch.pendingUserQuestions = null;
      break;
    case "session_identity":
      patch.sessionId = nextSessionId;
      break;
    case "input_state":
      patch.inputEnabled = event.payload.enabled;
      break;
    case "wait_state":
      patch.waitMessage = event.payload.active
        ? event.payload.message ?? "Working..."
        : null;
      break;
    case "processing_state":
      patch.processing = readProcessingState(event.payload);
      if (patch.processing === null && current.restoredInput) {
        patch.inputEnabled = true;
      }
      break;
    case "user_questions_requested":
      patch.pendingUserQuestions = readPendingUserQuestions(event.payload);
      patch.inputEnabled = false;
      break;
    case "user_questions_resolved":
      if (current.pendingUserQuestions?.prompt_id === event.payload.prompt_id) {
        patch.pendingUserQuestions = null;
      }
      break;
    case "usage_updated":
      if (event.payload.sub_agent_id) {
        break;
      }
      if (event.payload.scope === "session") {
        patch.sessionUsage = event.payload.usage;
      } else {
        patch.turnUsage = {
          usage: event.payload.usage,
          elapsedSeconds: event.payload.elapsed_seconds ?? undefined,
        };
      }
      break;
    case "message_added": {
      const payload = event.payload;
      patch.restoredInput = null;
      const item: TimelineItem = {
        kind: "message",
        itemId: payload.item_id,
        messageId: payload.message_id ?? undefined,
        partIds: readMessagePartIds(payload.part_ids),
        role: payload.role,
        content: payload.content,
        filePaths: payload.file_paths,
        imageAttachments: payload.image_attachments?.filter(isImageAttachment),
        markdown: payload.markdown ?? false,
        subAgentId: payload.sub_agent_id ?? undefined,
      };
      patch.items = upsertItem(current.items, item);
      patch.itemsVersion = current.itemsVersion + 1;
      break;
    }
    case "message_rekeyed": {
      const payload = event.payload;
      const rawItem = payload.item;
      if (!rawItem || typeof rawItem !== "object") {
        break;
      }
      const item = mapSnapshotItem({
        ...(rawItem as Record<string, unknown>),
        kind: "message",
      });
      if (!item) {
        break;
      }
      patch.restoredInput = null;
      patch.items = rekeyItem(current.items, payload.old_item_id, item);
      patch.itemsVersion = current.itemsVersion + 1;
      break;
    }
    case "message_removed": {
      const payload = event.payload;
      const itemId = payload.item_id;
      if (itemId) {
        patch.items = current.items.filter((item) => item.itemId !== itemId);
        patch.itemsVersion = current.itemsVersion + 1;
      }
      const restoredInput = payload.restore_input ?? "";
      if (restoredInput) {
        patch.restoredInput = restoredInput;
      }
      break;
    }
    case "thinking_updated": {
      const payload = event.payload;
      const item: TimelineItem = {
        kind: "thinking",
        itemId: payload.item_id,
        title: payload.title,
        content: payload.content,
        subAgentId: payload.sub_agent_id ?? undefined,
      };
      patch.items = upsertItem(current.items, item);
      patch.itemsVersion = current.itemsVersion + 1;
      break;
    }
    case "tool_group_added": {
      const payload = event.payload;
      const item: TimelineItem = {
        kind: "tool_group",
        itemId: payload.item_id,
        label: payload.label,
        status: payload.status ?? undefined,
        items: readToolGroupItems(payload.items),
        subAgentId: payload.sub_agent_id ?? undefined,
      };
      patch.items = upsertItem(current.items, item);
      patch.itemsVersion = current.itemsVersion + 1;
      break;
    }
    case "sub_agent_state": {
      const payload = event.payload;
      const subAgentId = payload.sub_agent_id;
      patch.subAgents = {
        ...current.subAgents,
        [subAgentId]: {
          title: payload.title,
          status: payload.status,
        },
      };
      break;
    }
    case "session_state":
      patch.sessionId = nextSessionId;
      if (event.payload.state === "ended") {
        if (nextSessionId) {
          patch.liveSessionId = null;
          patch.sessionEnded = false;
        } else {
          patch.sessionEnded = true;
        }
        patch.inputEnabled = false;
        patch.waitMessage = null;
        patch.processing = null;
        patch.fatalError = event.payload.fatal_error ?? null;
        patch.pendingUserQuestions = null;
      } else {
        patch.sessionEnded = false;
        patch.fatalError = null;
      }
      break;
    case "session_runtime_updated":
      patch.runtime = {
        provider_id: event.payload.provider_id ?? null,
        profile_id: event.payload.profile_id ?? null,
        provider: event.payload.provider,
        model: event.payload.model,
        reasoning_effort: event.payload.reasoning_effort,
        compact_threshold: event.payload.compact_threshold,
      };
      break;
    default:
      break;
  }

  return {
    state: {
      ...current,
      ...patch,
      sessionId: patch.sessionId ?? current.sessionId,
    },
    applied: true,
  };
}

export const useSessionStore = create<SessionStore>((set) => ({
  activeSessionKey: null,
  sessionsByKey: {},
  liveSessionIndex: {},
  sessionIndex: {},
  setActiveSession: (sessionKey) => set({ activeSessionKey: sessionKey }),
  hydrateSavedSession: (sessionId, items = [], lastEventSeq) =>
    set((state) => {
      const sessionKey = getSavedSessionKey(sessionId);
      const current = state.sessionsByKey[sessionKey] ?? createEmptySessionState(sessionId);
      const nextLiveSessionIndex = { ...state.liveSessionIndex };
      if (current.liveSessionId) {
        delete nextLiveSessionIndex[current.liveSessionId];
      }
      return {
        ...state,
        sessionsByKey: {
          ...state.sessionsByKey,
          [sessionKey]: {
            ...current,
            sessionId,
            items,
            itemsVersion: items.length,
            fatalError: null,
            // Reset live-session state so revisiting a saved session
            // does not keep stale liveSessionId / connection / flags
            // from a previously ended session.
            liveSessionId: null,
            connection: "disconnected",
            inputEnabled: false,
            waitMessage: null,
            processing: null,
            pendingUserQuestions: null,
            restoredInput: null,
            sessionEnded: false,
            // Set lastEventSeq from the server so the WS snapshot
            // replay skips events already covered by API history.
            // Use the server value directly (not Math.max) because the
            // current value may belong to a previous, ended live session
            // whose seq space is unrelated.
            lastEventSeq: typeof lastEventSeq === "number"
              ? lastEventSeq
              : 0,
          },
        },
        liveSessionIndex: nextLiveSessionIndex,
        sessionIndex: { ...state.sessionIndex, [sessionId]: sessionKey },
      };
    }),
  attachLiveSession: (sessionKey, session, options = {}) => {
    let resolvedKey = sessionKey;
    set((state) => {
      resolvedKey = session.session_id ? getSavedSessionKey(session.session_id) : sessionKey;
      let nextState = state;
      if (sessionKey !== resolvedKey) {
        nextState = moveSessionState(state, sessionKey, resolvedKey);
      }
      const current =
        nextState.sessionsByKey[resolvedKey]
        ?? createEmptySessionState(session.session_id);
      const returnedLastEventSeq = typeof session.last_event_seq === "number"
        ? session.last_event_seq
        : 0;
      const sameLiveSession = current.liveSessionId === session.live_session_id;
      const hasAppliedCurrentOrNewerStreamEvents = sameLiveSession
        && options.preserveEventCursor
        && current.lastEventSeq >= returnedLastEventSeq;
      return {
        ...nextState,
        sessionsByKey: {
          ...nextState.sessionsByKey,
          [resolvedKey]: {
            ...current,
            liveSessionId: session.live_session_id,
            sessionId: session.session_id,
            runtime: runtimeFromSession(session),
            inputEnabled: hasAppliedCurrentOrNewerStreamEvents ? current.inputEnabled : false,
            waitMessage: hasAppliedCurrentOrNewerStreamEvents ? current.waitMessage : null,
            processing: hasAppliedCurrentOrNewerStreamEvents ? current.processing : null,
            restoredInput: options.preserveItems ? current.restoredInput : null,
            sessionUsage: options.preserveItems ? current.sessionUsage : null,
            turnUsage: options.preserveItems ? current.turnUsage : null,
            sessionEnded: session.status === "ended",
            fatalError: session.fatal_error,
            items: options.preserveItems ? current.items : [],
            itemsVersion: options.preserveItems ? current.itemsVersion : 0,
            subAgents: options.preserveItems ? current.subAgents : {},
            // Event seq is scoped to one live stream. Preserve the cursor only
            // for the same stream. If saved-session submit returns a new live
            // run, reset so the new stream can replay the submitted turn.
            lastEventSeq: sameLiveSession
              ? options.preserveEventCursor
                ? current.lastEventSeq
                : Math.max(current.lastEventSeq, returnedLastEventSeq)
              : options.preserveEventCursor
                ? 0
                : returnedLastEventSeq,
          },
        },
        liveSessionIndex: {
          ...nextState.liveSessionIndex,
          [session.live_session_id]: resolvedKey,
        },
        sessionIndex: session.session_id
          ? { ...nextState.sessionIndex, [session.session_id]: resolvedKey }
          : nextState.sessionIndex,
      };
    });
    return resolvedKey;
  },
  hydrateLiveSnapshot: (sessionKey, session, snapshot) => {
    let resolvedKey = sessionKey;
    set((state) => {
      resolvedKey = snapshot.session_id ? getSavedSessionKey(snapshot.session_id) : sessionKey;
      let nextState = state;
      if (sessionKey !== resolvedKey) {
        nextState = moveSessionState(state, sessionKey, resolvedKey);
      }
      const current =
        nextState.sessionsByKey[resolvedKey]
        ?? createEmptySessionState(snapshot.session_id);
      const items = snapshot.items
        .map((item) => mapSnapshotItem(item))
        .filter((item): item is TimelineItem => item !== null);
      const savedEndedSnapshot = Boolean(snapshot.session_id && snapshot.session_ended);
      const nextLiveSessionId = savedEndedSnapshot ? null : session.live_session_id;
      const nextLiveSessionIndex = { ...nextState.liveSessionIndex };
      if (current.liveSessionId && current.liveSessionId !== nextLiveSessionId) {
        delete nextLiveSessionIndex[current.liveSessionId];
      }
      if (nextLiveSessionId) {
        nextLiveSessionIndex[nextLiveSessionId] = resolvedKey;
      }
      return {
        ...nextState,
        sessionsByKey: {
          ...nextState.sessionsByKey,
          [resolvedKey]: {
            ...current,
            liveSessionId: nextLiveSessionId,
            sessionId: snapshot.session_id,
            runtime: runtimeFromSession(session),
            inputEnabled: snapshot.input_enabled,
            waitMessage: snapshot.wait_message,
            processing: snapshot.processing,
            restoredInput: current.restoredInput,
            sessionUsage: snapshot.session_usage,
            turnUsage: snapshot.turn_usage
              ? {
                  usage: snapshot.turn_usage.usage,
                  elapsedSeconds:
                    typeof snapshot.turn_usage.elapsed_seconds === "number"
                      ? snapshot.turn_usage.elapsed_seconds
                      : undefined,
                }
              : null,
            sessionEnded: savedEndedSnapshot ? false : snapshot.session_ended,
            fatalError: snapshot.fatal_error,
            pendingUserQuestions: snapshot.pending_user_questions ?? null,
            items,
            itemsVersion: items.length,
            subAgents: snapshot.sub_agents,
            lastEventSeq: snapshot.last_event_seq,
          },
        },
        liveSessionIndex: nextLiveSessionIndex,
        sessionIndex: snapshot.session_id
          ? { ...nextState.sessionIndex, [snapshot.session_id]: resolvedKey }
          : nextState.sessionIndex,
      };
    });
    return resolvedKey;
  },
  updateRuntimeFromSession: (sessionKey, session) =>
    set((state) => {
      const current = state.sessionsByKey[sessionKey];
      if (!current) return state;
      return {
        ...state,
        sessionsByKey: {
          ...state.sessionsByKey,
          [sessionKey]: {
            ...current,
            runtime: runtimeFromSession(session),
          },
        },
      };
    }),
  setConnection: (sessionKey, connection) =>
    set((state) => {
      const current = state.sessionsByKey[sessionKey] ?? createEmptySessionState();
      return {
        ...state,
        sessionsByKey: {
          ...state.sessionsByKey,
          [sessionKey]: { ...current, connection },
        },
      };
    }),
  resetStreamState: (sessionKey, options = {}) =>
    set((state) => {
      const current = state.sessionsByKey[sessionKey];
      if (!current) return state;
      const nextLiveSessionIndex = { ...state.liveSessionIndex };
      if (current.liveSessionId && !options.preserveLiveSession) {
        delete nextLiveSessionIndex[current.liveSessionId];
      }
      if (current.liveSessionId && options.preserveLiveSession) {
        nextLiveSessionIndex[current.liveSessionId] = sessionKey;
      }
      return {
        ...state,
        sessionsByKey: {
          ...state.sessionsByKey,
          [sessionKey]: {
            ...createEmptySessionState(current.sessionId),
            sessionId: current.sessionId,
            liveSessionId: options.preserveLiveSession ? current.liveSessionId : null,
            items: options.preserveItems ? current.items : [],
            itemsVersion: options.preserveItems ? current.itemsVersion : 0,
            subAgents: options.preserveItems ? current.subAgents : {},
            connection: "disconnected",
          },
        },
        liveSessionIndex: nextLiveSessionIndex,
        sessionIndex: current.sessionId
          ? { ...state.sessionIndex, [current.sessionId]: sessionKey }
          : state.sessionIndex,
      };
    }),
  consumeRestoredInput: (sessionKey) =>
    set((state) => {
      const current = state.sessionsByKey[sessionKey];
      if (!current?.restoredInput) return state;
      return {
        ...state,
        sessionsByKey: {
          ...state.sessionsByKey,
          [sessionKey]: { ...current, restoredInput: null },
        },
      };
    }),
  applyEvent: (sessionKey, event, eventLiveSessionId = null) => {
    let result: ApplySessionEventResult = { sessionKey, applied: false };
    set((state) => {
      const target = resolveSessionEventTarget(
        state,
        sessionKey,
        event,
        eventLiveSessionId,
      );
      const resolvedKey = target.sessionKey;
      result = { sessionKey: resolvedKey, applied: false };
      let nextState = state;
      if (sessionKey !== resolvedKey && !(resolvedKey in state.sessionsByKey)) {
        const fallbackSession = state.sessionsByKey[sessionKey];
        if (
          fallbackSession
          && target.liveSessionId
          && fallbackSession.liveSessionId === target.liveSessionId
        ) {
          nextState = moveSessionState(state, sessionKey, resolvedKey);
        }
      }
      const existingSession = nextState.sessionsByKey[resolvedKey];
      const current =
        existingSession
        ?? createEmptySessionState(target.sessionId);
      const allowLiveSessionAdoption = !(
        target.liveSessionId
        && current.sessionId
        && !current.liveSessionId
      );
      const reduced = reduceSessionEvent(current, event as SessionWebEvent, {
        eventLiveSessionId: target.liveSessionId,
        allowLiveSessionAdoption,
      });
      if (!reduced.applied) {
        result = {
          sessionKey: resolvedKey,
          applied: false,
          reason: reduced.reason,
          reloadRequired: reduced.reloadRequired,
        };
        return nextState;
      }
      const nextSessionState = reduced.state;
      result = { sessionKey: resolvedKey, applied: true };

      const nextLiveSessionIndex = { ...nextState.liveSessionIndex };
      if (current.liveSessionId && current.liveSessionId !== nextSessionState.liveSessionId) {
        delete nextLiveSessionIndex[current.liveSessionId];
      }
      if (nextSessionState.liveSessionId) {
        nextLiveSessionIndex[nextSessionState.liveSessionId] = resolvedKey;
      }
      const nextSessionIndex = nextSessionState.sessionId
        ? { ...nextState.sessionIndex, [nextSessionState.sessionId]: resolvedKey }
        : nextState.sessionIndex;

      return {
        ...nextState,
        sessionsByKey: {
          ...nextState.sessionsByKey,
          [resolvedKey]: nextSessionState,
        },
        liveSessionIndex: nextLiveSessionIndex,
        sessionIndex: nextSessionIndex,
      };
    });
    return result;
  },
}));
