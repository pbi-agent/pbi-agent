import type {
  BootstrapPayload,
  ExpandedChatInput,
  FileMentionItem,
  ImageAttachment,
  LiveSession,
  SessionRecord,
  SlashCommandItem,
  TaskRecord,
} from "./types";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    headers,
    ...init,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function websocketUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}${path}`;
}

export async function fetchBootstrap(): Promise<BootstrapPayload> {
  return requestJson<BootstrapPayload>("/api/bootstrap");
}

export async function fetchSessions(): Promise<SessionRecord[]> {
  const result = await requestJson<{ sessions: SessionRecord[] }>("/api/sessions");
  return result.sessions;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await requestJson<void>(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

export async function searchFileMentions(
  query: string,
  limit = 8,
): Promise<FileMentionItem[]> {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  });
  const result = await requestJson<{ items: FileMentionItem[] }>(
    `/api/files/search?${params.toString()}`,
  );
  return result.items;
}

export async function searchSlashCommands(
  query: string,
  limit = 8,
): Promise<SlashCommandItem[]> {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  });
  const result = await requestJson<{ items: SlashCommandItem[] }>(
    `/api/slash-commands/search?${params.toString()}`,
  );
  return result.items;
}

export async function createChatSession(
  payload: Partial<{
    live_session_id: string;
    resume_session_id: string;
  }> = {},
): Promise<LiveSession> {
  const result = await requestJson<{ session: LiveSession }>("/api/chat/session", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return result.session;
}

export async function submitChatInput(
  liveSessionId: string,
  payload: {
    text: string;
    file_paths: string[];
    image_paths: string[];
    image_upload_ids: string[];
  },
): Promise<LiveSession> {
  const result = await requestJson<{ session: LiveSession }>(
    `/api/chat/session/${liveSessionId}/input`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
  return result.session;
}

export async function uploadChatImages(
  liveSessionId: string,
  files: File[],
): Promise<ImageAttachment[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const result = await requestJson<{ uploads: ImageAttachment[] }>(
    `/api/chat/session/${liveSessionId}/images`,
    {
      method: "POST",
      body: formData,
    },
  );
  return result.uploads;
}

export async function expandChatInput(text: string): Promise<ExpandedChatInput> {
  return requestJson<ExpandedChatInput>("/api/chat/expand-input", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export async function requestNewChat(liveSessionId: string): Promise<LiveSession> {
  const result = await requestJson<{ session: LiveSession }>(
    `/api/chat/session/${liveSessionId}/new-chat`,
    { method: "POST" },
  );
  return result.session;
}

export async function fetchTasks(): Promise<TaskRecord[]> {
  const result = await requestJson<{ tasks: TaskRecord[] }>("/api/tasks");
  return result.tasks;
}

export async function createTask(
  payload: Partial<TaskRecord> & { title: string; prompt: string },
): Promise<TaskRecord> {
  const result = await requestJson<{ task: TaskRecord }>("/api/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return result.task;
}

export async function updateTask(
  taskId: string,
  payload: Partial<TaskRecord> & { clear_session_id?: boolean },
): Promise<TaskRecord> {
  const result = await requestJson<{ task: TaskRecord }>(`/api/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return result.task;
}

export async function deleteTask(taskId: string): Promise<void> {
  await requestJson<void>(`/api/tasks/${taskId}`, { method: "DELETE" });
}

export async function runTask(taskId: string): Promise<TaskRecord> {
  const result = await requestJson<{ task: TaskRecord }>(`/api/tasks/${taskId}/run`, {
    method: "POST",
  });
  return result.task;
}
