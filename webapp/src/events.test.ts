import { parseSseEvent } from "./events";

describe("parseSseEvent", () => {
  it("parses valid SSE event envelopes", () => {
    const event = parseSseEvent(JSON.stringify({
      seq: 1,
      type: "input_state",
      created_at: "2026-05-04T00:00:00Z",
      payload: { enabled: true },
    }));

    expect(event?.type).toBe("input_state");
    if (event?.type !== "input_state") {
      throw new Error("expected input_state");
    }
    expect(event?.payload.enabled).toBe(true);
  });

  it("ignores malformed SSE messages", () => {
    expect(parseSseEvent("not-json")).toBeNull();
    expect(parseSseEvent(JSON.stringify({ seq: 1, type: "input_state" }))).toBeNull();
    expect(parseSseEvent(JSON.stringify({
      seq: 1,
      type: "input_state",
      created_at: "2026-05-04T00:00:00Z",
      payload: [],
    }))).toBeNull();
  });

  it.each([
    ["unknown type", { seq: 1, type: "unknown", created_at: "2026-05-04T00:00:00Z", payload: {} }],
    ["fractional seq", { seq: 1.5, type: "input_state", created_at: "2026-05-04T00:00:00Z", payload: { enabled: true } }],
    ["negative seq", { seq: -1, type: "input_state", created_at: "2026-05-04T00:00:00Z", payload: { enabled: true } }],
    ["non-number seq", { seq: "1", type: "input_state", created_at: "2026-05-04T00:00:00Z", payload: { enabled: true } }],
    ["missing created_at", { seq: 1, type: "input_state", payload: { enabled: true } }],
  ])("rejects malformed SSE envelopes: %s", (_label, event) => {
    expect(parseSseEvent(JSON.stringify(event))).toBeNull();
  });

  it.each([
    ["input_state", { seq: 1, type: "input_state", payload: { enabled: "yes" } }],
    ["session_state", { seq: 1, type: "session_state", payload: { state: "done" } }],
    ["replay", { seq: 0, type: "server.replay_incomplete", payload: { snapshot_required: "true" } }],
    ["message_added", { seq: 1, type: "message_added", payload: { item_id: "m1", role: "assistant" } }],
    ["usage_updated", { seq: 1, type: "usage_updated", payload: { scope: "other", usage: {} } }],
  ])("rejects malformed SSE payloads: %s", (_label, event) => {
    expect(parseSseEvent(JSON.stringify({
      created_at: "2026-05-04T00:00:00Z",
      ...event,
    }))).toBeNull();
  });

  it.each([
    { seq: 0, type: "server.connected", payload: {} },
    { seq: 1, type: "session_created", payload: { session: {} } },
    { seq: 2, type: "live_session_started", payload: { live_session: {} } },
  ])("accepts representative valid control and app events", (event) => {
    expect(parseSseEvent(JSON.stringify({
      created_at: "2026-05-04T00:00:00Z",
      ...event,
    }))?.type).toBe(event.type);
  });
});
