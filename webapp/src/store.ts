import { create } from "zustand";

import type {
  ImageAttachment,
  LiveSession,
  LiveSessionRuntime,
  LiveSessionSnapshot,
  TimelineItem,
  UsagePayload,
  WebEvent,
} from "./types";

export type ConnectionState = "disconnected" | "connecting" | "connected";

export type SubAgentState = {
  title: string;
  status: string;
};

export type ChatRuntimeState = {
  liveSessionId: string | null;
  sessionId: string | null;
  runtime: LiveSessionRuntime | null;
  connection: ConnectionState;
  inputEnabled: boolean;
  waitMessage: string | null;
  sessionUsage: UsagePayload | null;
  turnUsage: { usage: UsagePayload | null; elapsedSeconds?: number } | null;
  sessionEnded: boolean;
  fatalError: string | null;
  items: TimelineItem[];
  itemsVersion: number;
  subAgents: Record<string, SubAgentState>;
  lastEventSeq: number;
};

type ChatStore = {
  activeChatKey: string | null;
  chatsByKey: Record<string, ChatRuntimeState>;
  liveSessionIndex: Record<string, string>;
  sessionIndex: Record<string, string>;
  setActiveChat: (chatKey: string | null) => void;
  hydrateSavedChat: (sessionId: string, items?: TimelineItem[]) => void;
  attachLiveSession: (
    chatKey: string,
    session: LiveSession,
    options?: { preserveItems?: boolean },
  ) => string;
  hydrateLiveSnapshot: (
    chatKey: string,
    session: LiveSession,
    snapshot: LiveSessionSnapshot,
  ) => string;
  updateRuntimeFromSession: (chatKey: string, session: LiveSession) => void;
  setConnection: (chatKey: string, connection: ConnectionState) => void;
  applyEvent: (chatKey: string, event: WebEvent) => string;
};

function createEmptyChatState(sessionId: string | null = null): ChatRuntimeState {
  return {
    liveSessionId: null,
    sessionId,
    runtime: null,
    connection: "disconnected",
    inputEnabled: false,
    waitMessage: null,
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

export function getSavedChatKey(sessionId: string): string {
  return `session:${sessionId}`;
}

export function getLiveChatKey(liveSessionId: string): string {
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

function mapSnapshotItem(raw: Record<string, unknown>): TimelineItem | null {
  const kind = raw.kind;
  const itemId = typeof raw.itemId === "string" ? raw.itemId : null;
  if (!itemId || typeof kind !== "string") return null;
  if (kind === "message") {
    return {
      kind: "message",
      itemId,
      role: (raw.role as "user" | "assistant" | "notice" | "error" | "debug") ?? "assistant",
      content: String(raw.content ?? ""),
      filePaths: Array.isArray(raw.file_paths)
        ? raw.file_paths.filter((value): value is string => typeof value === "string")
        : undefined,
      imageAttachments: Array.isArray(raw.image_attachments)
        ? raw.image_attachments.filter(
            (value): value is ImageAttachment =>
              Boolean(value)
              && typeof value === "object"
              && typeof (value as ImageAttachment).upload_id === "string",
          )
        : undefined,
      markdown: Boolean(raw.markdown),
      subAgentId:
        typeof raw.sub_agent_id === "string" ? raw.sub_agent_id : undefined,
    };
  }
  if (kind === "thinking") {
    return {
      kind: "thinking",
      itemId,
      title: String(raw.title ?? "Thinking"),
      content: String(raw.content ?? ""),
      subAgentId:
        typeof raw.sub_agent_id === "string" ? raw.sub_agent_id : undefined,
    };
  }
  if (kind === "tool_group") {
    return {
      kind: "tool_group",
      itemId,
      label: String(raw.label ?? "Tool calls"),
      items: Array.isArray(raw.items)
        ? (raw.items as { text: string; classes?: string }[])
        : [],
      subAgentId:
        typeof raw.sub_agent_id === "string" ? raw.sub_agent_id : undefined,
    };
  }
  return null;
}

function moveChatState(
  state: ChatStore,
  fromKey: string,
  toKey: string,
): ChatStore {
  if (fromKey === toKey || !(fromKey in state.chatsByKey)) {
    return state;
  }
  const chatState = state.chatsByKey[fromKey];
  const nextChatsByKey = { ...state.chatsByKey };
  delete nextChatsByKey[fromKey];
  nextChatsByKey[toKey] = chatState;

  const nextLiveSessionIndex = Object.fromEntries(
    Object.entries(state.liveSessionIndex).map(([id, key]) => [id, key === fromKey ? toKey : key]),
  );
  const nextSessionIndex = Object.fromEntries(
    Object.entries(state.sessionIndex).map(([id, key]) => [id, key === fromKey ? toKey : key]),
  );

  return {
    ...state,
    chatsByKey: nextChatsByKey,
    liveSessionIndex: nextLiveSessionIndex,
    sessionIndex: nextSessionIndex,
    activeChatKey: state.activeChatKey === fromKey ? toKey : state.activeChatKey,
  };
}

export const useChatStore = create<ChatStore>((set, get) => ({
  activeChatKey: null,
  chatsByKey: {},
  liveSessionIndex: {},
  sessionIndex: {},
  setActiveChat: (chatKey) => set({ activeChatKey: chatKey }),
  hydrateSavedChat: (sessionId, items = []) =>
    set((state) => {
      const chatKey = getSavedChatKey(sessionId);
      const current = state.chatsByKey[chatKey] ?? createEmptyChatState(sessionId);
      return {
        ...state,
        chatsByKey: {
          ...state.chatsByKey,
          [chatKey]: {
            ...current,
            sessionId,
            items,
            itemsVersion: items.length,
            fatalError: null,
          },
        },
        sessionIndex: { ...state.sessionIndex, [sessionId]: chatKey },
      };
    }),
  attachLiveSession: (chatKey, session, options = {}) => {
    let resolvedKey = chatKey;
    set((state) => {
      resolvedKey = session.session_id ? getSavedChatKey(session.session_id) : chatKey;
      let nextState = state;
      if (chatKey !== resolvedKey) {
        nextState = moveChatState(state, chatKey, resolvedKey);
      }
      const current =
        nextState.chatsByKey[resolvedKey]
        ?? createEmptyChatState(session.session_id);
      return {
        ...nextState,
        chatsByKey: {
          ...nextState.chatsByKey,
          [resolvedKey]: {
            ...current,
            liveSessionId: session.live_session_id,
            sessionId: session.session_id,
            runtime: runtimeFromSession(session),
            inputEnabled: false,
            waitMessage: null,
            sessionUsage: options.preserveItems ? current.sessionUsage : null,
            turnUsage: options.preserveItems ? current.turnUsage : null,
            sessionEnded: session.status === "ended",
            fatalError: session.fatal_error,
            items: options.preserveItems ? current.items : [],
            itemsVersion: options.preserveItems ? current.itemsVersion : 0,
            subAgents: options.preserveItems ? current.subAgents : {},
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
  hydrateLiveSnapshot: (chatKey, session, snapshot) => {
    let resolvedKey = chatKey;
    set((state) => {
      resolvedKey = snapshot.session_id ? getSavedChatKey(snapshot.session_id) : chatKey;
      let nextState = state;
      if (chatKey !== resolvedKey) {
        nextState = moveChatState(state, chatKey, resolvedKey);
      }
      const current =
        nextState.chatsByKey[resolvedKey]
        ?? createEmptyChatState(snapshot.session_id);
      const items = snapshot.items
        .map((item) => mapSnapshotItem(item))
        .filter((item): item is TimelineItem => item !== null);
      return {
        ...nextState,
        chatsByKey: {
          ...nextState.chatsByKey,
          [resolvedKey]: {
            ...current,
            liveSessionId: session.live_session_id,
            sessionId: snapshot.session_id,
            runtime: runtimeFromSession(session),
            inputEnabled: snapshot.input_enabled,
            waitMessage: snapshot.wait_message,
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
  updateRuntimeFromSession: (chatKey, session) =>
    set((state) => {
      const current = state.chatsByKey[chatKey];
      if (!current) return state;
      return {
        ...state,
        chatsByKey: {
          ...state.chatsByKey,
          [chatKey]: {
            ...current,
            runtime: runtimeFromSession(session),
          },
        },
      };
    }),
  setConnection: (chatKey, connection) =>
    set((state) => {
      const current = state.chatsByKey[chatKey] ?? createEmptyChatState();
      return {
        ...state,
        chatsByKey: {
          ...state.chatsByKey,
          [chatKey]: { ...current, connection },
        },
      };
    }),
  applyEvent: (chatKey, event) => {
    let resolvedKey = chatKey;
    set((state) => {
      const payload = event.payload;
      const nextSessionId =
        typeof payload.session_id === "string" ? payload.session_id : null;
      resolvedKey = nextSessionId ? getSavedChatKey(nextSessionId) : chatKey;
      let nextState = state;
      if (chatKey !== resolvedKey) {
        nextState = moveChatState(state, chatKey, resolvedKey);
      }
      const current =
        nextState.chatsByKey[resolvedKey]
        ?? createEmptyChatState(nextSessionId);
      const patch: Partial<ChatRuntimeState> = { lastEventSeq: event.seq };

      switch (event.type) {
        case "chat_reset":
          patch.items = [];
          patch.itemsVersion = 0;
          patch.subAgents = {};
          patch.waitMessage = null;
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
          patch.waitMessage = payload.active ? String(payload.message || "Working...") : null;
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
            role:
              (payload.role as "user" | "assistant" | "notice" | "error" | "debug")
              ?? "assistant",
            content: String(payload.content || ""),
            filePaths: Array.isArray(payload.file_paths)
              ? payload.file_paths.filter((value): value is string => typeof value === "string")
              : undefined,
            imageAttachments: Array.isArray(payload.image_attachments)
              ? payload.image_attachments.filter(
                  (value): value is ImageAttachment =>
                    Boolean(value)
                    && typeof value === "object"
                    && typeof value.upload_id === "string",
                )
              : undefined,
            markdown: Boolean(payload.markdown),
            subAgentId:
              typeof payload.sub_agent_id === "string" ? payload.sub_agent_id : undefined,
          };
          patch.items = upsertItem(current.items, item);
          patch.itemsVersion = current.itemsVersion + 1;
          break;
        }
        case "thinking_updated": {
          const item: TimelineItem = {
            kind: "thinking",
            itemId: String(payload.item_id),
            title: String(payload.title || "Thinking"),
            content: String(payload.content || ""),
            subAgentId:
              typeof payload.sub_agent_id === "string" ? payload.sub_agent_id : undefined,
          };
          patch.items = upsertItem(current.items, item);
          patch.itemsVersion = current.itemsVersion + 1;
          break;
        }
        case "tool_group_added": {
          const item: TimelineItem = {
            kind: "tool_group",
            itemId: String(payload.item_id),
            label: String(payload.label || "Tool calls"),
            items: Array.isArray(payload.items)
              ? (payload.items as { text: string; classes?: string }[])
              : [],
            subAgentId:
              typeof payload.sub_agent_id === "string" ? payload.sub_agent_id : undefined,
          };
          patch.items = upsertItem(current.items, item);
          patch.itemsVersion = current.itemsVersion + 1;
          break;
        }
        case "sub_agent_state": {
          const subAgentId = String(payload.sub_agent_id || "");
          patch.subAgents = {
            ...current.subAgents,
            [subAgentId]: {
              title: String(payload.title || "sub_agent"),
              status: String(payload.status || "running"),
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

      const nextChatState: ChatRuntimeState = {
        ...current,
        ...patch,
        sessionId: patch.sessionId ?? current.sessionId,
      };

      const nextLiveSessionIndex = current.liveSessionId
        ? { ...nextState.liveSessionIndex, [current.liveSessionId]: resolvedKey }
        : nextState.liveSessionIndex;
      const nextSessionIndex = nextChatState.sessionId
        ? { ...nextState.sessionIndex, [nextChatState.sessionId]: resolvedKey }
        : nextState.sessionIndex;

      return {
        ...nextState,
        chatsByKey: {
          ...nextState.chatsByKey,
          [resolvedKey]: nextChatState,
        },
        liveSessionIndex: nextLiveSessionIndex,
        sessionIndex: nextSessionIndex,
      };
    });
    return resolvedKey;
  },
}));
