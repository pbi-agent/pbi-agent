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
    ["welcome", { seq: 1, type: "welcome", payload: { interactive: "yes" } }],
  ])("rejects malformed SSE payloads: %s", (_label, event) => {
    expect(parseSseEvent(JSON.stringify({
      created_at: "2026-05-04T00:00:00Z",
      ...event,
    }))).toBeNull();
  });

  it.each([
    ["non-array file_paths", { file_paths: "docs/spec.md" }],
    ["non-string file path", { file_paths: ["docs/spec.md", 2] }],
    ["non-array image_attachments", { image_attachments: {} }],
    ["non-object image attachment", { image_attachments: ["upload-1"] }],
    ["missing image attachment upload_id", { image_attachments: [{ name: "image.png", preview_url: "/api/uploads/upload-1" }] }],
    ["missing image attachment name", { image_attachments: [{ upload_id: "upload-1", preview_url: "/api/uploads/upload-1" }] }],
    ["missing image attachment preview_url", { image_attachments: [{ upload_id: "upload-1", name: "image.png" }] }],
    ["non-object part_ids", { part_ids: [] }],
    ["missing part_ids content", { part_ids: { file_paths: [] } }],
    ["non-string part_ids content", { part_ids: { content: 1 } }],
    ["non-array part_ids file_paths", { part_ids: { content: "m1:content", file_paths: "m1:file-path:0" } }],
    ["non-string part_ids image attachment", { part_ids: { content: "m1:content", image_attachments: [1] } }],
  ])("rejects malformed message_added optional payload fields: %s", (_label, optionalFields) => {
    expect(parseSseEvent(JSON.stringify({
      seq: 1,
      type: "message_added",
      created_at: "2026-05-04T00:00:00Z",
      payload: {
        item_id: "m1",
        role: "user",
        content: "Hello",
        ...optionalFields,
      },
    }))).toBeNull();
  });

  it("accepts valid message_added optional payload fields", () => {
    const event = parseSseEvent(JSON.stringify({
      seq: 1,
      type: "message_added",
      created_at: "2026-05-04T00:00:00Z",
      payload: {
        item_id: "m1",
        role: "user",
        content: "Hello docs/spec.md",
        file_paths: ["docs/spec.md"],
        image_attachments: [{
          upload_id: "upload-1",
          name: "image.png",
          preview_url: "/api/uploads/upload-1",
        }],
        part_ids: {
          content: "m1:content",
          file_paths: ["m1:file-path:0"],
          image_attachments: ["m1:image:upload-1"],
        },
      },
    }));

    expect(event?.type).toBe("message_added");
  });

  it.each([
    ["missing old_item_id", { item: { item_id: "m2", role: "assistant", content: "Hello" } }],
    ["non-object item", { old_item_id: "pending-1", item: null }],
    ["missing item_id", { old_item_id: "pending-1", item: { role: "assistant", content: "Hello" } }],
    ["non-string item_id", { old_item_id: "pending-1", item: { item_id: 2, role: "assistant", content: "Hello" } }],
    ["invalid role", { old_item_id: "pending-1", item: { item_id: "m2", role: "system", content: "Hello" } }],
    ["missing content", { old_item_id: "pending-1", item: { item_id: "m2", role: "assistant" } }],
    ["non-string content", { old_item_id: "pending-1", item: { item_id: "m2", role: "assistant", content: [] } }],
  ])("rejects malformed message rekey payloads: %s", (_label, payload) => {
    expect(parseSseEvent(JSON.stringify({
      seq: 1,
      type: "message_rekeyed",
      created_at: "2026-05-04T00:00:00Z",
      payload,
    }))).toBeNull();
  });

  it.each([
    ["non-array file_paths", { file_paths: "docs/spec.md" }],
    ["non-string file path", { file_paths: ["docs/spec.md", false] }],
    ["non-array image_attachments", { image_attachments: {} }],
    ["missing image attachment preview_url", { image_attachments: [{ upload_id: "upload-1", name: "image.png" }] }],
    ["non-object part_ids", { part_ids: [] }],
    ["non-array part_ids image_attachments", { part_ids: { content: "m2:content", image_attachments: "m2:image:upload-1" } }],
  ])("rejects malformed message rekey item optional fields: %s", (_label, optionalFields) => {
    expect(parseSseEvent(JSON.stringify({
      seq: 1,
      type: "message_rekeyed",
      created_at: "2026-05-04T00:00:00Z",
      payload: {
        old_item_id: "pending-1",
        item: {
          item_id: "m2",
          role: "assistant",
          content: "Hello",
          ...optionalFields,
        },
      },
    }))).toBeNull();
  });

  it("accepts valid message rekey payloads", () => {
    const event = parseSseEvent(JSON.stringify({
      seq: 1,
      type: "message_rekeyed",
      created_at: "2026-05-04T00:00:00Z",
      payload: {
        old_item_id: "pending-1",
        item: {
          item_id: "m2",
          role: "assistant",
          content: "Hello",
          metadata: { source: "test" },
          part_ids: null,
        },
      },
    }));

    expect(event?.type).toBe("message_rekeyed");
  });

  it.each([
    ["missing prompt_id", { questions: [{ question_id: "q1", question: "Pick?", suggestions: ["A", "B", "C"] }] }],
    ["empty questions", { prompt_id: "prompt-1", questions: [] }],
    ["missing question_id", { prompt_id: "prompt-1", questions: [{ question: "Pick?", suggestions: ["A", "B", "C"] }] }],
    ["missing question", { prompt_id: "prompt-1", questions: [{ question_id: "q1", suggestions: ["A", "B", "C"] }] }],
    ["too few suggestions", { prompt_id: "prompt-1", questions: [{ question_id: "q1", question: "Pick?", suggestions: ["A", "B"] }] }],
    ["too many suggestions", { prompt_id: "prompt-1", questions: [{ question_id: "q1", question: "Pick?", suggestions: ["A", "B", "C", "D"] }] }],
    ["non-string suggestion", { prompt_id: "prompt-1", questions: [{ question_id: "q1", question: "Pick?", suggestions: ["A", 2, "C"] }] }],
    ["fractional recommended index", { prompt_id: "prompt-1", questions: [{ question_id: "q1", question: "Pick?", suggestions: ["A", "B", "C"], recommended_suggestion_index: 1.5 }] }],
    ["out-of-range recommended index", { prompt_id: "prompt-1", questions: [{ question_id: "q1", question: "Pick?", suggestions: ["A", "B", "C"], recommended_suggestion_index: 3 }] }],
  ])("rejects malformed user questions requested payloads: %s", (_label, payload) => {
    expect(parseSseEvent(JSON.stringify({
      seq: 1,
      type: "user_questions_requested",
      created_at: "2026-05-04T00:00:00Z",
      payload,
    }))).toBeNull();
  });

  it("accepts valid user questions requested payloads", () => {
    const event = parseSseEvent(JSON.stringify({
      seq: 1,
      type: "user_questions_requested",
      created_at: "2026-05-04T00:00:00Z",
      payload: {
        prompt_id: "prompt-1",
        questions: [
          {
            question_id: "question-1",
            question: "Which path?",
            suggestions: ["A", "B", "C"],
            recommended_suggestion_index: 2,
          },
        ],
      },
    }));

    expect(event?.type).toBe("user_questions_requested");
  });

  it.each([
    { seq: 0, type: "server.connected", payload: {} },
    { seq: 1, type: "welcome", payload: { interactive: true, model: "gpt-5.5", reasoning_effort: "low", single_turn_hint: null } },
    { seq: 1, type: "session_created", payload: { session: {} } },
    { seq: 2, type: "live_session_started", payload: { live_session: {} } },
  ])("accepts representative valid control and app events", (event) => {
    expect(parseSseEvent(JSON.stringify({
      created_at: "2026-05-04T00:00:00Z",
      ...event,
    }))?.type).toBe(event.type);
  });

  it.each([
    ["absent", undefined],
    ["null", null],
    ["integer", 2],
  ])("accepts valid subscriber queue overflow replay-incomplete with oldest_available_seq %s", (_label, oldestAvailableSeq) => {
    const payload: Record<string, unknown> = {
      reason: "subscriber_queue_overflow",
      requested_since: 1,
      resolved_since: 1,
      latest_seq: 4,
      snapshot_required: true,
    };
    if (oldestAvailableSeq !== undefined) {
      payload.oldest_available_seq = oldestAvailableSeq;
    }

    const event = parseSseEvent(JSON.stringify({
      seq: 4,
      type: "server.replay_incomplete",
      created_at: "2026-05-04T00:00:00Z",
      payload,
    }));

    expect(event?.type).toBe("server.replay_incomplete");
  });

  it.each([
    ["fractional", 1.5],
    ["string", "1"],
    ["object", {}],
  ])("rejects malformed oldest_available_seq: %s", (_label, oldestAvailableSeq) => {
    expect(parseSseEvent(JSON.stringify({
      seq: 4,
      type: "server.replay_incomplete",
      created_at: "2026-05-04T00:00:00Z",
      payload: {
        reason: "subscriber_queue_overflow",
        requested_since: 1,
        resolved_since: 1,
        latest_seq: 4,
        oldest_available_seq: oldestAvailableSeq,
        snapshot_required: true,
      },
    }))).toBeNull();
  });
});
