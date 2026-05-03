import type { WebEvent } from "./types";

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
    || typeof value.type !== "string"
    || typeof value.created_at !== "string"
    || !isRecord(payload)
  ) {
    return null;
  }
  return value as WebEvent;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
