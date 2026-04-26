import { create } from "zustand";

import type {
  ApplyPatchToolMetadata,
  ImageAttachment,
  LiveSession,
  LiveSessionRuntime,
  LiveSessionSnapshot,
  ProcessingPhase,
  ProcessingState,
  TimelineItem,
  TimelineToolGroupEntry,
  ToolCallStatus,
  ToolGroupStatus,
  UsagePayload,
  WebEvent,
} from "./types";

export type ConnectionState = "disconnected" | "connecting" | "connected";

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
  sessionUsage: UsagePayload | null;
  turnUsage: { usage: UsagePayload | null; elapsedSeconds?: number } | null;
  sessionEnded: boolean;
  fatalError: string | null;
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
    options?: { preserveItems?: boolean },
  ) => string;
  hydrateLiveSnapshot: (
    sessionKey: string,
    session: LiveSession,
    snapshot: LiveSessionSnapshot,
  ) => string;
  updateRuntimeFromSession: (sessionKey: string, session: LiveSession) => void;
  setConnection: (sessionKey: string, connection: ConnectionState) => void;
  applyEvent: (sessionKey: string, event: WebEvent, liveSessionId?: string | null) => string;
};

function createEmptySessionState(sessionId: string | null = null): SessionRuntimeState {
  return {
    liveSessionId: null,
    sessionId,
    runtime: null,
    connection: "disconnected",
    inputEnabled: false,
    waitMessage: null,
    processing: null,
    sessionUsage: null,
    turnUsage: null,
    sessionEnded: false,
    fatalError: null,
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

function readString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function readOptionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
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

function readApplyPatchMetadata(value: unknown): ApplyPatchToolMetadata | undefined {
  if (value === null || typeof value !== "object") {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  return {
    tool_name: readOptionalString(record.tool_name),
    path: readOptionalString(record.path),
    operation: readOptionalString(record.operation),
    success: readBoolean(record.success),
    detail: readOptionalString(record.detail),
    diff: readOptionalString(record.diff),
    diff_line_numbers: readDiffLineNumbers(record.diff_line_numbers),
    call_id: readOptionalString(record.call_id),
    status: readToolCallStatus(record.status),
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
      metadata: readApplyPatchMetadata(record.metadata),
    };
  });
}

function mapSnapshotItem(raw: Record<string, unknown>): TimelineItem | null {
  const kind = raw.kind;
  const itemId = typeof raw.itemId === "string" ? raw.itemId : null;
  if (!itemId || typeof kind !== "string") return null;
  if (kind === "message") {
    return {
      kind: "message",
      itemId,
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
      return {
        ...nextState,
        sessionsByKey: {
          ...nextState.sessionsByKey,
          [resolvedKey]: {
            ...current,
            liveSessionId: session.live_session_id,
            sessionId: session.session_id,
            runtime: runtimeFromSession(session),
            inputEnabled: false,
            waitMessage: null,
            processing: null,
            sessionUsage: options.preserveItems ? current.sessionUsage : null,
            turnUsage: options.preserveItems ? current.turnUsage : null,
            sessionEnded: session.status === "ended",
            fatalError: session.fatal_error,
            items: options.preserveItems ? current.items : [],
            itemsVersion: options.preserveItems ? current.itemsVersion : 0,
            subAgents: options.preserveItems ? current.subAgents : {},
            // When reattaching the same live session, carry forward the
            // high-water mark so the WS snapshot replay skips events
            // already covered by API history.  When attaching a *new*
            // live session (seq restarts from 1), reset to the server's
            // value so we don't suppress the new session's events.
            lastEventSeq:
              current.liveSessionId === session.live_session_id
                ? Math.max(
                    current.lastEventSeq,
                    typeof session.last_event_seq === "number" ? session.last_event_seq : 0,
                  )
                : (typeof session.last_event_seq === "number" ? session.last_event_seq : 0),
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
      return {
        ...nextState,
        sessionsByKey: {
          ...nextState.sessionsByKey,
          [resolvedKey]: {
            ...current,
            liveSessionId: session.live_session_id,
            sessionId: snapshot.session_id,
            runtime: runtimeFromSession(session),
            inputEnabled: snapshot.input_enabled,
            waitMessage: snapshot.wait_message,
            processing: snapshot.processing,
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
            sessionEnded: snapshot.session_ended,
            fatalError: snapshot.fatal_error,
            items,
            itemsVersion: items.length,
            subAgents: snapshot.sub_agents,
            lastEventSeq: snapshot.last_event_seq,
          },
        },
        liveSessionIndex: {
          ...nextState.liveSessionIndex,
          [session.live_session_id]: resolvedKey,
        },
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
  applyEvent: (sessionKey, event, eventLiveSessionId = null) => {
    let resolvedKey = sessionKey;
    set((state) => {
      const payload = event.payload;
      const nextSessionId =
        typeof payload.session_id === "string" ? payload.session_id : null;
      resolvedKey = nextSessionId ? getSavedSessionKey(nextSessionId) : sessionKey;
      let nextState = state;
      if (sessionKey !== resolvedKey) {
        nextState = moveSessionState(state, sessionKey, resolvedKey);
      }
      const existingSession = nextState.sessionsByKey[resolvedKey];
      const current =
        existingSession
        ?? createEmptySessionState(nextSessionId);
      if (
        existingSession
        && eventLiveSessionId
        && (current.liveSessionId || current.sessionId)
        && current.liveSessionId !== eventLiveSessionId
      ) {
        return nextState;
      }
      // Skip events already processed — prevents duplicates when the
      // WebSocket reconnects and replays its snapshot over items that
      // were already hydrated from the API (which use different itemIds).
      if (event.seq <= current.lastEventSeq) {
        return nextState;
      }
      const patch: Partial<SessionRuntimeState> = { lastEventSeq: event.seq };
      if (eventLiveSessionId && !current.liveSessionId && !current.sessionId) {
        patch.liveSessionId = eventLiveSessionId;
      }

      switch (event.type) {
        case "session_reset":
          patch.items = [];
          patch.itemsVersion = 0;
          patch.subAgents = {};
          patch.waitMessage = null;
          patch.processing = null;
          patch.turnUsage = null;
          patch.sessionEnded = false;
          patch.fatalError = null;
          break;
        case "session_identity":
          patch.sessionId = nextSessionId;
          break;
        case "input_state":
          patch.inputEnabled = Boolean(payload.enabled);
          break;
        case "wait_state":
          patch.waitMessage = payload.active
            ? readString(payload.message, "Working...")
            : null;
          break;
        case "processing_state":
          patch.processing = readProcessingState(payload);
          break;
        case "usage_updated":
          if (payload.scope === "session") {
            patch.sessionUsage = payload.usage as UsagePayload;
          } else {
            patch.turnUsage = {
              usage: payload.usage as UsagePayload,
              elapsedSeconds:
                typeof payload.elapsed_seconds === "number" ? payload.elapsed_seconds : undefined,
            };
          }
          break;
        case "message_added": {
          const item: TimelineItem = {
            kind: "message",
            itemId: String(payload.item_id),
            role: readTimelineRole(payload.role),
            content: readString(payload.content),
            filePaths: Array.isArray(payload.file_paths)
              ? payload.file_paths.filter((value): value is string => typeof value === "string")
              : undefined,
            imageAttachments: Array.isArray(payload.image_attachments)
              ? payload.image_attachments.filter(isImageAttachment)
              : undefined,
            markdown: Boolean(payload.markdown),
            subAgentId: readOptionalString(payload.sub_agent_id),
          };
          patch.items = upsertItem(current.items, item);
          patch.itemsVersion = current.itemsVersion + 1;
          break;
        }
        case "thinking_updated": {
          const item: TimelineItem = {
            kind: "thinking",
            itemId: String(payload.item_id),
            title: readString(payload.title, "Thinking"),
            content: readString(payload.content),
            subAgentId: readOptionalString(payload.sub_agent_id),
          };
          patch.items = upsertItem(current.items, item);
          patch.itemsVersion = current.itemsVersion + 1;
          break;
        }
        case "tool_group_added": {
          const item: TimelineItem = {
            kind: "tool_group",
            itemId: String(payload.item_id),
            label: readString(payload.label, "Tool calls"),
            status: readToolGroupStatus(payload.status),
            items: readToolGroupItems(payload.items),
            subAgentId: readOptionalString(payload.sub_agent_id),
          };
          patch.items = upsertItem(current.items, item);
          patch.itemsVersion = current.itemsVersion + 1;
          break;
        }
        case "sub_agent_state": {
          const subAgentId = readString(payload.sub_agent_id);
          patch.subAgents = {
            ...current.subAgents,
            [subAgentId]: {
              title: readString(payload.title, "sub_agent"),
              status: readString(payload.status, "running"),
            },
          };
          break;
        }
        case "session_state":
          patch.sessionId = nextSessionId;
          if (payload.state === "ended") {
            patch.sessionEnded = true;
            patch.inputEnabled = false;
            patch.waitMessage = null;
            patch.processing = null;
            patch.fatalError =
              typeof payload.fatal_error === "string" ? payload.fatal_error : null;
          } else {
            patch.sessionEnded = false;
            patch.fatalError = null;
          }
          break;
        case "session_runtime_updated":
          if (
            typeof payload.provider === "string"
            && typeof payload.model === "string"
            && typeof payload.reasoning_effort === "string"
          ) {
            patch.runtime = {
              provider_id:
                typeof payload.provider_id === "string" ? payload.provider_id : null,
              profile_id:
                typeof payload.profile_id === "string" ? payload.profile_id : null,
              provider: payload.provider,
              model: payload.model,
              reasoning_effort: payload.reasoning_effort,
            };
          }
          break;
        default:
          break;
      }

      const nextSessionState: SessionRuntimeState = {
        ...current,
        ...patch,
        sessionId: patch.sessionId ?? current.sessionId,
      };

      const nextLiveSessionIndex = current.liveSessionId
        ? { ...nextState.liveSessionIndex, [current.liveSessionId]: resolvedKey }
        : nextState.liveSessionIndex;
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
    return resolvedKey;
  },
}));
