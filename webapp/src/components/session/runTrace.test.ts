import type { ChildRunDetail, ObservabilityEventSummary, RunDetail, RunSession } from "../../types";
import { buildRunTrace, countSpans, formatSpanDuration, type TraceSpan } from "./runTrace";

const T0 = Date.parse("2026-04-27T10:00:00Z");

function at(offsetMs: number): string {
  return new Date(T0 + offsetMs).toISOString();
}

function makeRun(overrides: Partial<RunSession> = {}): RunSession {
  return {
    run_session_id: "root",
    session_id: "session-1",
    parent_run_session_id: null,
    agent_name: "main",
    agent_type: "session_turn",
    provider: "openai",
    provider_id: null,
    profile_id: null,
    model: "gpt-5.4",
    reasoning_effort: null,
    status: "completed",
    started_at: at(0),
    ended_at: at(10_000),
    total_duration_ms: 10_000,
    input_tokens: 0,
    cached_input_tokens: 0,
    cache_write_tokens: 0,
    cache_write_1h_tokens: 0,
    output_tokens: 0,
    reasoning_tokens: 0,
    provider_total_tokens: 0,
    estimated_cost_usd: 0,
    total_tool_calls: 0,
    total_api_calls: 0,
    error_count: 0,
    metadata: null,
    ...overrides,
  };
}

let nextStep = 0;

function makeEvent(overrides: Partial<ObservabilityEventSummary>): ObservabilityEventSummary {
  nextStep += 1;
  return {
    run_session_id: "root",
    session_id: "session-1",
    step_index: nextStep,
    event_type: "model_call",
    timestamp: at(0),
    duration_ms: null,
    provider: "openai",
    model: "gpt-5.4",
    url: null,
    tool_name: null,
    tool_call_id: null,
    tool_duration_ms: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    cached_input_tokens: null,
    reasoning_tokens: null,
    status_code: null,
    success: true,
    error_message: null,
    has_payload: false,
    ...overrides,
  };
}

/** A tool call that ran from `startMs` to `endMs` after the root run started. */
function toolCall(startMs: number, endMs: number, overrides: Partial<ObservabilityEventSummary> = {}) {
  return makeEvent({
    event_type: "tool_call",
    tool_name: "sub_agent",
    timestamp: at(endMs),
    duration_ms: endMs - startMs,
    ...overrides,
  });
}

function childRun(
  id: string,
  startMs: number,
  durationMs: number,
  overrides: Partial<ChildRunDetail> & { parent?: string } = {},
): ChildRunDetail {
  const { parent = "root", ...rest } = overrides;
  return {
    run: makeRun({
      run_session_id: id,
      parent_run_session_id: parent,
      agent_name: id,
      started_at: at(startMs),
      ended_at: at(startMs + durationMs),
      total_duration_ms: durationMs,
    }),
    events: [],
    parent_tool_call_id: null,
    ...rest,
  };
}

function detail(overrides: Partial<RunDetail> = {}): RunDetail {
  return { run: makeRun(), events: [], child_runs: [], ...overrides };
}

function labels(span: TraceSpan): string[] {
  return span.children.map((child) => child.label);
}

describe("buildRunTrace", () => {
  beforeEach(() => {
    nextStep = 0;
  });

  it("keeps recorded events in order and hides bookkeeping markers", () => {
    const root = buildRunTrace(
      detail({
        events: [
          makeEvent({ event_type: "run_start" }),
          makeEvent({ event_type: "hook_started" }),
          makeEvent({ event_type: "hook_completed", timestamp: at(200), duration_ms: 150 }),
          makeEvent({ event_type: "agent_step_start" }),
          makeEvent({ event_type: "model_call_start" }),
          makeEvent({ event_type: "model_call_retry", success: false, error_message: "429" }),
          makeEvent({ event_type: "model_call", timestamp: at(1_000), duration_ms: 1_000 }),
          makeEvent({ event_type: "agent_step_end" }),
          makeEvent({
            event_type: "tool_call",
            tool_name: "shell",
            timestamp: at(1_500),
            duration_ms: null,
            tool_duration_ms: 500,
            success: false,
          }),
          makeEvent({ event_type: "error", success: false, error_message: "boom" }),
          makeEvent({ event_type: "turn_interrupted", success: null }),
          makeEvent({ event_type: "run_end", duration_ms: 10_000 }),
        ],
      }),
    );

    expect(root).toMatchObject({ label: "main", type: "agent", durationMs: 10_000, status: "ok" });
    expect(root.bar).toEqual({ offset: 0, width: 1 });
    expect(root.children.map((span) => [span.label, span.type, span.status])).toEqual([
      ["hook", "hook", "ok"],
      ["retry", "error", "failed"],
      ["gpt-5.4", "chat", "ok"],
      ["shell", "tool", "failed"],
      ["error", "error", "failed"],
      ["turn interrupted", "event", null],
    ]);
    expect(root.children[0].durationMs).toBe(150);
    expect(root.children[1].bar).toBeNull();
    expect(root.children[1].durationMs).toBeNull();
    expect(root.children[3].durationMs).toBe(500);
    expect(countSpans(root)).toBe(7);
  });

  it("positions bars by start offset and share of the root duration", () => {
    const root = buildRunTrace(
      detail({
        events: [
          makeEvent({ timestamp: at(3_000), duration_ms: 2_000 }),
          makeEvent({ timestamp: at(10_000), duration_ms: 5_000 }),
        ],
      }),
    );

    expect(root.children[0].bar).toEqual({ offset: 0.1, width: 0.2 });
    expect(root.children[1].bar).toEqual({ offset: 0.5, width: 0.5 });
  });

  it("measures the run from its run_start event rather than the run row's creation", () => {
    const root = buildRunTrace(
      detail({
        run: makeRun({ started_at: at(-5_000), total_duration_ms: 10_000 }),
        events: [
          makeEvent({ event_type: "run_start", timestamp: at(0) }),
          makeEvent({ timestamp: at(10_000), duration_ms: 5_000 }),
        ],
      }),
    );

    expect(root.startMs).toBe(T0);
    expect(root.bar).toEqual({ offset: 0, width: 1 });
    expect(root.children[0].bar).toEqual({ offset: 0.5, width: 0.5 });
  });

  it("clamps early starts and keeps tiny spans visible", () => {
    const root = buildRunTrace(
      detail({
        events: [
          makeEvent({ timestamp: at(1_000), duration_ms: 3_000 }),
          makeEvent({ timestamp: at(10_000), duration_ms: 1 }),
          makeEvent({ timestamp: at(5_000), duration_ms: null }),
        ],
      }),
    );

    const [early, tiny, untimed] = root.children.map((span) => span.bar);
    expect(early).toEqual({ offset: 0, width: 0.1 });
    expect(tiny?.width).toBe(0.005);
    expect((tiny?.offset ?? 0) + (tiny?.width ?? 0)).toBeLessThanOrEqual(1);
    expect(untimed).toBeNull();
  });

  it("widens the time scale to cover a sub-agent that outlives its parent run", () => {
    const root = buildRunTrace(
      detail({
        events: [toolCall(8_000, 8_010, { tool_call_id: "call_bg" })],
        child_runs: [
          childRun("background", 8_000, 32_000, {
            parent_tool_call_id: "call_bg",
            events: [makeEvent({ run_session_id: "background", timestamp: at(40_000), duration_ms: 10_000 })],
          }),
        ],
      }),
    );

    // The scale spans 0..40 s, so the 10 s root run covers a quarter of it.
    expect(root.bar).toEqual({ offset: 0, width: 0.25 });
    const background = root.children[0].children[0];
    expect(background.bar?.offset).toBeCloseTo(0.2);
    expect(background.bar?.width).toBeCloseTo(0.8);
    expect(background.children[0].bar).toEqual({ offset: 0.75, width: 0.25 });
  });

  it("measures an active run against the current time", () => {
    const root = buildRunTrace(
      detail({
        run: makeRun({ status: "running", ended_at: null, total_duration_ms: null }),
        events: [makeEvent({ timestamp: at(2_000), duration_ms: 1_000 })],
      }),
      T0 + 4_000,
    );

    expect(root.status).toBe("running");
    expect(root.durationMs).toBe(4_000);
    expect(root.children[0].bar).toEqual({ offset: 0.25, width: 0.25 });
  });

  it("shows a model call that has started but not returned as running", () => {
    const events = [
      makeEvent({ event_type: "run_start" }),
      makeEvent({ event_type: "model_call_start", timestamp: at(1_000) }),
    ];
    const running = makeRun({ status: "running", ended_at: null, total_duration_ms: 4_000 });

    const root = buildRunTrace(detail({ run: running, events }), T0 + 4_000);
    expect(root.children).toHaveLength(1);
    expect(root.children[0]).toMatchObject({
      label: "gpt-5.4",
      type: "chat",
      status: "running",
      durationMs: 3_000,
      bar: { offset: 0.25, width: 0.75 },
    });
    expect(root.children[0].event).toBe(events[1]);

    // Once the call is recorded, or the run is over, nothing is pending.
    const finished = [...events, makeEvent({ timestamp: at(3_000), duration_ms: 2_000 })];
    expect(labels(buildRunTrace(detail({ run: running, events: finished }), T0 + 4_000))).toEqual([
      "gpt-5.4",
    ]);
    expect(buildRunTrace(detail({ events })).children).toEqual([]);
  });

  it("omits the root bar when the run has no usable duration", () => {
    const root = buildRunTrace(
      detail({
        run: makeRun({ status: "stale", ended_at: null, total_duration_ms: null }),
        events: [makeEvent({ timestamp: at(2_000), duration_ms: 1_000 })],
      }),
    );

    expect(root.durationMs).toBeNull();
    expect(root.bar).toBeNull();
    expect(root.children[0].durationMs).toBe(1_000);
    expect(root.children[0].bar).toEqual({ offset: 0.5, width: 0.5 });
  });

  it("nests a sub-agent run under the tool call with the matching call id", () => {
    const root = buildRunTrace(
      detail({
        events: [
          toolCall(1_000, 1_010, { tool_call_id: "call_bg" }),
          toolCall(1_000, 6_000, { tool_call_id: "call_fg" }),
        ],
        child_runs: [childRun("background", 2_000, 7_000, { parent_tool_call_id: "call_bg" })],
      }),
    );

    expect(labels(root)).toEqual(["sub_agent", "sub_agent"]);
    expect(labels(root.children[0])).toEqual(["background"]);
    expect(root.children[1].children).toEqual([]);
    expect(root.children[0].children[0]).toMatchObject({
      type: "agent",
      bar: { offset: 0.2, width: 0.7 },
    });
  });

  it("keeps a running sub-agent under a placeholder for its unfinished tool call", () => {
    const running = makeRun({ status: "running", ended_at: null, total_duration_ms: 5_000 });
    const child = childRun("explorer", 2_000, 3_000, { parent_tool_call_id: "call_1" });
    child.run.status = "running";

    const live = buildRunTrace(detail({ run: running, child_runs: [child] }), T0 + 5_000);
    const placeholder = live.children[0];
    expect(placeholder).toMatchObject({
      label: "sub_agent",
      type: "tool",
      status: "running",
      durationMs: 3_000,
      bar: { offset: 0.4, width: 0.6 },
    });
    expect(placeholder.event).toBeUndefined();
    expect(labels(placeholder)).toEqual(["explorer"]);

    // The recorded call takes over the placeholder's id, so the row stays mounted.
    const done = buildRunTrace(
      detail({
        run: running,
        events: [toolCall(2_000, 5_000, { tool_call_id: "call_1" })],
        child_runs: [child],
      }),
      T0 + 5_000,
    );
    expect(done.children[0].id).toBe(placeholder.id);
    expect(done.children[0].status).toBe("ok");
    expect(labels(done.children[0])).toEqual(["explorer"]);
  });

  it("appends a sub-agent run to its parent run when no tool call is linked", () => {
    const root = buildRunTrace(
      detail({
        events: [toolCall(1_000, 9_000)],
        child_runs: [
          childRun("unlinked", 1_050, 1_000),
          childRun("orphan", 5_000, 1_000, { parent_tool_call_id: "missing" }),
          childRun("unknown-parent", 6_000, 1_000, { parent: "gone" }),
        ],
      }),
    );

    expect(labels(root)).toEqual(["sub_agent", "unlinked", "orphan", "unknown-parent"]);
    expect(root.children[0].children).toEqual([]);
  });

  it("nests sub-agents of sub-agents", () => {
    const root = buildRunTrace(
      detail({
        events: [toolCall(1_000, 9_000, { tool_call_id: "call_1" })],
        child_runs: [
          childRun("child", 1_100, 7_000, {
            parent_tool_call_id: "call_1",
            events: [
              toolCall(2_000, 6_000, { run_session_id: "child", tool_call_id: "call_2" }),
              makeEvent({ run_session_id: "child", timestamp: at(7_000), duration_ms: 500 }),
            ],
          }),
          childRun("grandchild", 2_100, 3_000, {
            parent: "child",
            parent_tool_call_id: "call_2",
            events: [makeEvent({ run_session_id: "grandchild", timestamp: at(4_000), duration_ms: 1_000 })],
          }),
        ],
      }),
    );

    const child = root.children[0].children[0];
    expect(child.label).toBe("child");
    expect(labels(child)).toEqual(["sub_agent", "gpt-5.4"]);
    const grandchild = child.children[0].children[0];
    expect(grandchild.label).toBe("grandchild");
    expect(grandchild.children[0].bar).toEqual({ offset: 0.3, width: 0.1 });
    expect(countSpans(root)).toBe(7);
  });
});

describe("formatSpanDuration", () => {
  it.each([
    [736, "0.736 s"],
    [4_100, "4.1 s"],
    [1_000, "1 s"],
    [0, "0 s"],
    [12_345, "12.3 s"],
    [59_980, "1m 0s"],
    [72_000, "1m 12s"],
    [119_600, "2m 0s"],
  ])("formats %d ms as %s", (ms, expected) => {
    expect(formatSpanDuration(ms)).toBe(expected);
  });
});
