import type { ObservabilityEventSummary, RunDetail, RunSession } from "../../types";

export type TraceSpanType = "agent" | "chat" | "tool" | "hook" | "error" | "event";
export type TraceSpanStatus = "ok" | "failed" | "running";

export type TraceSpan = {
  id: string;
  label: string;
  type: TraceSpanType;
  durationMs: number | null;
  startMs: number | null;
  endMs: number | null;
  /** Bar start and width as fractions (0..1) of the whole trace; null when the span has no bar. */
  bar: { offset: number; width: number } | null;
  status: TraceSpanStatus | null;
  children: TraceSpan[];
  /** Source event for spans built from a recorded event. */
  event?: ObservabilityEventSummary;
  /** Source run for agent spans. */
  run?: RunSession;
};

const MIN_BAR_WIDTH = 0.005;
const TERMINAL_RUN_STATUSES = new Set(["completed", "interrupted", "ended", "failed", "stale"]);
/** Bookkeeping events that carry no span of their own. */
const MARKER_EVENT_TYPES = new Set([
  "run_start",
  "run_end",
  "agent_step_start",
  "agent_step_end",
  "model_call_start",
  "hook_started",
]);

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function isRunActive(run: RunSession): boolean {
  return !TERMINAL_RUN_STATUSES.has(run.status);
}

function runTiming(
  run: RunSession,
  events: ObservabilityEventSummary[],
  nowMs: number,
): Pick<TraceSpan, "startMs" | "durationMs" | "endMs"> {
  // The recorded duration is measured from the tracer start (its run_start
  // event), which can be later than the run row's creation time.
  const runStart = events.find((event) => event.event_type === "run_start");
  const startMs = parseTime(runStart?.timestamp) ?? parseTime(run.started_at);
  let durationMs = run.total_duration_ms;
  if (durationMs == null && startMs != null) {
    const endMs = parseTime(run.ended_at) ?? (isRunActive(run) ? nowMs : null);
    durationMs = endMs == null ? null : Math.max(0, endMs - startMs);
  }
  return {
    startMs,
    durationMs,
    endMs: startMs != null && durationMs != null ? startMs + durationMs : null,
  };
}

function eventSpanId(event: ObservabilityEventSummary): string {
  return event.event_type === "tool_call" && event.tool_call_id
    ? toolCallSpanId(event.run_session_id, event.tool_call_id)
    : `${event.run_session_id}:${event.step_index}`;
}

function toolCallSpanId(runSessionId: string, toolCallId: string): string {
  return `${runSessionId}:call:${toolCallId}`;
}

function eventSpan(event: ObservabilityEventSummary): TraceSpan | null {
  if (MARKER_EVENT_TYPES.has(event.event_type)) return null;
  let type: TraceSpanType;
  let label: string;
  switch (event.event_type) {
    case "model_call":
      type = "chat";
      label = event.model ?? event.provider ?? "model";
      break;
    case "tool_call":
      type = "tool";
      label = event.tool_name ?? "tool";
      break;
    case "hook_completed":
      type = "hook";
      label = "hook";
      break;
    case "model_call_retry":
      type = "error";
      label = "retry";
      break;
    case "error":
      type = "error";
      label = "error";
      break;
    default:
      type = "event";
      label = event.event_type.replaceAll("_", " ");
  }
  const durationMs = event.duration_ms ?? event.tool_duration_ms;
  const endMs = parseTime(event.timestamp);
  return {
    id: eventSpanId(event),
    label,
    type,
    durationMs,
    startMs: endMs != null && durationMs != null ? endMs - durationMs : endMs,
    endMs,
    bar: null,
    status: event.success === false || type === "error" ? "failed" : event.success === true ? "ok" : null,
    children: [],
    event,
  };
}

/** A span that started at `startMs` and has not finished yet. */
function runningSpan(
  span: Pick<TraceSpan, "id" | "label" | "type"> & Partial<TraceSpan>,
  startMs: number | null,
  nowMs: number,
): TraceSpan {
  return {
    bar: null,
    children: [],
    ...span,
    startMs,
    endMs: startMs == null ? null : Math.max(startMs, nowMs),
    durationMs: startMs == null ? null : Math.max(0, nowMs - startMs),
    status: "running",
  };
}

function runSpan(run: RunSession, events: ObservabilityEventSummary[], nowMs: number): TraceSpan {
  const children: TraceSpan[] = [];
  let pendingModelCall: ObservabilityEventSummary | null = null;
  for (const event of events) {
    if (event.event_type === "model_call_start") pendingModelCall = event;
    else if (event.event_type === "model_call") pendingModelCall = null;
    const span = eventSpan(event);
    if (span) children.push(span);
  }
  if (pendingModelCall && isRunActive(run)) {
    children.push(
      runningSpan(
        {
          id: eventSpanId(pendingModelCall),
          label: pendingModelCall.model ?? pendingModelCall.provider ?? "model",
          type: "chat",
          event: pendingModelCall,
        },
        parseTime(pendingModelCall.timestamp),
        nowMs,
      ),
    );
  }
  return {
    id: run.run_session_id,
    label: run.agent_name ?? run.agent_type ?? "run",
    type: "agent",
    ...runTiming(run, events, nowMs),
    bar: null,
    status: run.status === "failed" ? "failed" : isRunActive(run) ? "running" : "ok",
    children,
    run,
  };
}

/** Places a sub-agent run under the tool call that started it. */
function attachChildRun(parent: TraceSpan, child: TraceSpan, toolCallId: string | null, nowMs: number): void {
  const parentRun = parent.run;
  if (toolCallId && parentRun) {
    const id = toolCallSpanId(parentRun.run_session_id, toolCallId);
    const host = parent.children.find((span) => span.id === id);
    if (host) {
      host.children.push(child);
      return;
    }
    if (isRunActive(parentRun)) {
      // A tool call is only recorded once it returns; show it as running under
      // the id the finished call will get, so the row keeps its place.
      parent.children.push(
        runningSpan({ id, label: "sub_agent", type: "tool", children: [child] }, child.startMs, nowMs),
      );
      return;
    }
  }
  parent.children.push(child);
}

function forEachSpan(span: TraceSpan, visit: (span: TraceSpan) => void): void {
  visit(span);
  for (const child of span.children) forEachSpan(child, visit);
}

/** Scales every bar to the window from the root's start to the last recorded end. */
function assignBars(root: TraceSpan): void {
  const windowStart = root.startMs;
  if (windowStart == null) return;
  let windowEnd = windowStart;
  forEachSpan(root, (span) => {
    if (span.endMs != null) windowEnd = Math.max(windowEnd, span.endMs);
  });
  const windowMs = windowEnd - windowStart;
  if (windowMs <= 0) return;
  forEachSpan(root, (span) => {
    if (span.startMs == null || span.durationMs == null) return;
    const start = Math.min(Math.max(span.startMs, windowStart), windowEnd);
    const end = Math.min(Math.max(span.startMs + span.durationMs, start), windowEnd);
    const width = Math.max((end - start) / windowMs, MIN_BAR_WIDTH);
    span.bar = { offset: Math.min((start - windowStart) / windowMs, 1 - width), width };
  });
}

/** Builds the span tree for a run: run > model/tool calls, sub-agent runs under their tool call. */
export function buildRunTrace(detail: RunDetail, nowMs: number = Date.now()): TraceSpan {
  const root = runSpan(detail.run, detail.events, nowMs);
  const spansByRunId = new Map<string, TraceSpan>([[root.id, root]]);
  const children = detail.child_runs.map((child) => ({
    child,
    span: runSpan(child.run, child.events, nowMs),
  }));
  for (const { span } of children) spansByRunId.set(span.id, span);
  for (const { child, span } of children) {
    const parentId = child.run.parent_run_session_id;
    const parent = (parentId && parentId !== span.id ? spansByRunId.get(parentId) : undefined) ?? root;
    attachChildRun(parent, span, child.parent_tool_call_id, nowMs);
  }
  assignBars(root);
  return root;
}

export function countSpans(span: TraceSpan): number {
  return span.children.reduce((total, child) => total + countSpans(child), 1);
}

export function formatSpanDuration(ms: number): string {
  const seconds = ms / 1000;
  if (seconds < 10) return `${Number(seconds.toFixed(3))} s`;
  if (seconds < 59.95) return `${seconds.toFixed(1)} s`;
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}m ${whole % 60}s`;
}

export type SpanTokens = { input: number; output: number; cached: number; reasoning: number };

/** Token usage of a model call or an agent run; null for spans without usage. */
export function spanTokens(span: TraceSpan): SpanTokens | null {
  if (span.type === "agent" && span.run) {
    const run = span.run;
    if (!run.input_tokens && !run.output_tokens) return null;
    return {
      input: run.input_tokens,
      output: run.output_tokens,
      cached: run.cached_input_tokens,
      reasoning: run.reasoning_tokens,
    };
  }
  const event = span.event;
  if (span.type !== "chat" || !event || event.event_type !== "model_call") return null;
  if (event.prompt_tokens == null && event.completion_tokens == null) return null;
  return {
    input: event.prompt_tokens ?? 0,
    output: event.completion_tokens ?? 0,
    cached: event.cached_input_tokens ?? 0,
    reasoning: event.reasoning_tokens ?? 0,
  };
}
