import { create } from "zustand";

import type {
  ImageAttachment,
  LiveSession,
  LiveSessionRuntime,
  TimelineItem,
  UsagePayload,
  WebEvent,
} from "./types";

type ConnectionState = "disconnected" | "connecting" | "connected";

type SubAgentState = {
  title: string;
  status: string;
};

type ChatState = {
  liveSessionId: string | null;
  resumeSessionId: string | null;
  runtime: LiveSessionRuntime | null;
  connection: ConnectionState;
  inputEnabled: boolean;
  waitMessage: string | null;
  sessionUsage: UsagePayload | null;
  turnUsage: { usage: UsagePayload; elapsedSeconds?: number } | null;
  sessionEnded: boolean;
  fatalError: string | null;
  items: TimelineItem[];
  itemsVersion: number;
  subAgents: Record<string, SubAgentState>;
  lastEventSeq: number;
  setRouteState: (resumeSessionId: string | null, items?: TimelineItem[]) => void;
  attachLiveSession: (session: LiveSession, preserveItems?: boolean) => void;
  updateRuntimeFromSession: (session: LiveSession) => void;
  setConnection: (connection: ConnectionState) => void;
  clearTimeline: () => void;
  applyEvent: (event: WebEvent) => void;
};

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

export const useChatStore = create<ChatState>((set) => ({
  liveSessionId: null,
  resumeSessionId: null,
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
  setRouteState: (resumeSessionId, items = []) =>
    set({
      liveSessionId: null,
      resumeSessionId,
      runtime: null,
      connection: "disconnected",
      inputEnabled: false,
      waitMessage: null,
      sessionUsage: null,
      turnUsage: null,
      sessionEnded: false,
      fatalError: null,
      items,
      itemsVersion: items.length,
      subAgents: {},
      lastEventSeq: 0,
    }),
  attachLiveSession: (session, preserveItems = false) =>
    set((state) => ({
      liveSessionId: session.live_session_id,
      resumeSessionId: session.resume_session_id,
      runtime: runtimeFromSession(session),
      connection: state.connection,
      inputEnabled: false,
      waitMessage: null,
      sessionUsage: null,
      turnUsage: null,
      sessionEnded: false,
      fatalError: null,
      items: preserveItems ? state.items : [],
      itemsVersion: preserveItems ? state.itemsVersion : 0,
      subAgents: {},
      lastEventSeq: 0,
    })),
  updateRuntimeFromSession: (session) =>
    set({
      runtime: runtimeFromSession(session),
    }),
  setConnection: (connection) => set({ connection }),
  clearTimeline: () =>
    set({
      items: [],
      itemsVersion: 0,
      subAgents: {},
      waitMessage: null,
      turnUsage: null,
      sessionEnded: false,
      fatalError: null,
    }),
  applyEvent: (event) =>
    set((state) => {
      const payload = event.payload;
      const nextState: Partial<ChatState> = { lastEventSeq: event.seq };

      switch (event.type) {
        case "chat_reset":
          nextState.items = [];
          nextState.itemsVersion = 0;
          nextState.subAgents = {};
          nextState.waitMessage = null;
          nextState.turnUsage = null;
          nextState.sessionEnded = false;
          nextState.fatalError = null;
          return { ...state, ...nextState };
        case "session_identity":
          nextState.resumeSessionId =
            typeof payload.resume_session_id === "string"
              ? payload.resume_session_id
              : null;
          return { ...state, ...nextState };
        case "input_state":
          nextState.inputEnabled = Boolean(payload.enabled);
          return { ...state, ...nextState };
        case "wait_state":
          nextState.waitMessage = payload.active
            ? String(payload.message || "Working...")
            : null;
          return { ...state, ...nextState };
        case "usage_updated":
          if (payload.scope === "session") {
            nextState.sessionUsage = payload.usage as UsagePayload;
          } else {
            nextState.turnUsage = {
              usage: payload.usage as UsagePayload,
              elapsedSeconds:
                typeof payload.elapsed_seconds === "number"
                  ? payload.elapsed_seconds
                  : undefined,
            };
          }
          return { ...state, ...nextState };
        case "message_added": {
          const item: TimelineItem = {
            kind: "message",
            itemId: String(payload.item_id),
            role: (payload.role as
              | "user"
              | "assistant"
              | "notice"
              | "error"
              | "debug") ?? "assistant",
            content: String(payload.content || ""),
            filePaths: Array.isArray(payload.file_paths)
              ? payload.file_paths
                  .filter((value): value is string => typeof value === "string")
              : undefined,
            imageAttachments: Array.isArray(payload.image_attachments)
              ? payload.image_attachments.filter(
                  (value): value is ImageAttachment =>
                    Boolean(value) &&
                    typeof value === "object" &&
                    typeof value.upload_id === "string" &&
                    typeof value.name === "string" &&
                    typeof value.mime_type === "string" &&
                    typeof value.byte_count === "number" &&
                    typeof value.preview_url === "string",
                )
              : undefined,
            markdown: Boolean(payload.markdown),
            subAgentId:
              typeof payload.sub_agent_id === "string"
                ? payload.sub_agent_id
                : undefined,
          } as TimelineItem;
          nextState.items = upsertItem(state.items, item);
          nextState.itemsVersion = state.itemsVersion + 1;
          return { ...state, ...nextState };
        }
        case "thinking_updated": {
          const item: TimelineItem = {
            kind: "thinking",
            itemId: String(payload.item_id),
            title: String(payload.title || "Thinking"),
            content: String(payload.content || ""),
            subAgentId:
              typeof payload.sub_agent_id === "string"
                ? payload.sub_agent_id
                : undefined,
          };
          nextState.items = upsertItem(state.items, item);
          nextState.itemsVersion = state.itemsVersion + 1;
          return { ...state, ...nextState };
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
              typeof payload.sub_agent_id === "string"
                ? payload.sub_agent_id
                : undefined,
          };
          nextState.items = upsertItem(state.items, item);
          nextState.itemsVersion = state.itemsVersion + 1;
          return { ...state, ...nextState };
        }
        case "sub_agent_state": {
          const subAgentId = String(payload.sub_agent_id || "");
          nextState.subAgents = {
            ...state.subAgents,
            [subAgentId]: {
              title: String(payload.title || "sub_agent"),
              status: String(payload.status || "running"),
            },
          };
          return { ...state, ...nextState };
        }
        case "session_state":
          if ("resume_session_id" in payload) {
            nextState.resumeSessionId =
              typeof payload.resume_session_id === "string"
                ? payload.resume_session_id
                : null;
          }
          if (payload.state === "ended") {
            nextState.sessionEnded = true;
            nextState.inputEnabled = false;
            nextState.waitMessage = null;
            nextState.fatalError =
              typeof payload.fatal_error === "string"
                ? payload.fatal_error
                : null;
          } else {
            nextState.sessionEnded = false;
            nextState.fatalError = null;
          }
          return { ...state, ...nextState };
        case "session_runtime_updated":
          if (
            typeof payload.provider === "string"
            && typeof payload.model === "string"
            && typeof payload.reasoning_effort === "string"
          ) {
            nextState.runtime = {
              provider_id:
                typeof payload.provider_id === "string" ? payload.provider_id : null,
              profile_id:
                typeof payload.profile_id === "string" ? payload.profile_id : null,
              provider: payload.provider,
              model: payload.model,
              reasoning_effort: payload.reasoning_effort,
            };
          }
          return { ...state, ...nextState };
        default:
          return { ...state, ...nextState };
      }
    }),
}));
