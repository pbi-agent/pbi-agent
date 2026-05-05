import type { WebEvent } from "./types";

const EVENT_TYPES = new Set([
  "server.connected",
  "server.heartbeat",
  "server.replay_incomplete",
  "session_reset",
  "session_identity",
  "input_state",
  "wait_state",
  "processing_state",
  "user_questions_requested",
  "user_questions_resolved",
  "usage_updated",
  "message_added",
  "message_rekeyed",
  "message_removed",
  "thinking_updated",
  "tool_group_added",
  "sub_agent_state",
  "session_state",
  "session_runtime_updated",
  "session_created",
  "session_updated",
  "board_stages_updated",
  "task_updated",
  "task_deleted",
  "live_session_started",
  "live_session_updated",
  "live_session_bound",
  "live_session_ended",
]);

const MESSAGE_ROLES = new Set(["user", "assistant", "notice", "error", "debug"]);

export function parseSseEvent(data: string): WebEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return null;
  }
  if (!isRecord(value)) {
    return null;
  }
  const payload = value.payload;
  if (
    typeof value.seq !== "number"
    || !Number.isInteger(value.seq)
    || value.seq < 0
    || typeof value.type !== "string"
    || typeof value.created_at !== "string"
    || !isRecord(payload)
    || !EVENT_TYPES.has(value.type)
    || !isValidPayload(value.type, payload)
  ) {
    return null;
  }
  return value as WebEvent;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isReplayReason(value: unknown): boolean {
  return value === "cursor_too_old"
    || value === "cursor_ahead"
    || value === "subscriber_queue_overflow";
}

function isValidUserQuestionsRequestedPayload(payload: Record<string, unknown>): boolean {
  if (!isString(payload.prompt_id) || !Array.isArray(payload.questions) || payload.questions.length === 0) {
    return false;
  }
  return payload.questions.every((question) => {
    if (!isRecord(question)) return false;
    if (!isString(question.question_id) || !isString(question.question)) return false;
    if (
      !Array.isArray(question.suggestions)
      || question.suggestions.length !== 3
      || !question.suggestions.every(isString)
    ) {
      return false;
    }
    if (!("recommended_suggestion_index" in question)) return true;
    const index = question.recommended_suggestion_index;
    return typeof index === "number" && Number.isInteger(index) && index >= 0 && index <= 2;
  });
}

function isValidPayload(type: string, payload: Record<string, unknown>): boolean {
  switch (type) {
    case "server.replay_incomplete":
      return isReplayReason(payload.reason)
        && Number.isInteger(payload.requested_since)
        && Number.isInteger(payload.resolved_since)
        && Number.isInteger(payload.latest_seq)
        && (!("oldest_available_seq" in payload)
          || payload.oldest_available_seq === null
          || Number.isInteger(payload.oldest_available_seq))
        && typeof payload.snapshot_required === "boolean";
    case "input_state":
      return typeof payload.enabled === "boolean";
    case "wait_state":
    case "processing_state":
      return typeof payload.active === "boolean";
    case "user_questions_requested":
      return isValidUserQuestionsRequestedPayload(payload);
    case "user_questions_resolved":
      return isString(payload.prompt_id);
    case "usage_updated":
      return (payload.scope === "session" || payload.scope === "turn")
        && isRecord(payload.usage);
    case "message_added":
      return isString(payload.item_id)
        && MESSAGE_ROLES.has(String(payload.role))
        && isString(payload.content);
    case "message_rekeyed":
      return isString(payload.old_item_id) && isRecord(payload.item);
    case "message_removed":
      return isString(payload.item_id);
    case "thinking_updated":
      return isString(payload.item_id)
        && isString(payload.title)
        && isString(payload.content);
    case "tool_group_added":
      return isString(payload.item_id) && isString(payload.label);
    case "sub_agent_state":
      return isString(payload.sub_agent_id)
        && isString(payload.title)
        && isString(payload.status);
    case "session_state":
      return payload.state === "starting"
        || payload.state === "running"
        || payload.state === "ended";
    case "session_runtime_updated":
      return isString(payload.provider)
        && isString(payload.model)
        && isString(payload.reasoning_effort)
        && typeof payload.compact_threshold === "number";
    default:
      return true;
  }
}
