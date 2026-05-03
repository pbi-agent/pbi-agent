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
});
