import type {
  BoardStage,
  BootstrapPayload,
  ConfigBootstrapPayload,
  ExpandedChatInput,
  FileMentionItem,
  HistoryItem,
  ImageAttachment,
  LiveSession,
  LiveSessionSnapshot,
  ModelProfileView,
  ProviderView,
  SessionDetailPayload,
  SessionRecord,
  SlashCommandItem,
  TaskRecord,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    ...init,
    headers, // must come after ...init so Content-Type is not overwritten
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new ApiError(
      payload.detail || `Request failed: ${response.status}`,
      response.status,
    );
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

export async function fetchConfigBootstrap(): Promise<ConfigBootstrapPayload> {
  return requestJson<ConfigBootstrapPayload>("/api/config/bootstrap");
}

export async function fetchSessions(): Promise<SessionRecord[]> {
  const result = await requestJson<{ sessions: SessionRecord[] }>("/api/sessions");
  return result.sessions;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await requestJson<void>(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

export async function fetchSessionDetail(sessionId: string): Promise<SessionDetailPayload> {
  return requestJson<{
    session: SessionRecord;
    history_items: HistoryItem[];
    active_live_session: LiveSession | null;
  }>(`/api/sessions/${sessionId}`);
}

export async function fetchLiveSessions(): Promise<LiveSession[]> {
  const result = await requestJson<{ live_sessions: LiveSession[] }>("/api/live-sessions");
  return result.live_sessions;
}

export async function fetchLiveSessionDetail(
  liveSessionId: string,
): Promise<{ live_session: LiveSession; snapshot: LiveSessionSnapshot }> {
  return requestJson(`/api/live-sessions/${liveSessionId}`);
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
    session_id: string;
    profile_id: string | null;
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
    profile_id?: string | null;
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

export async function requestNewChat(
  liveSessionId: string,
  profileId: string | null = null,
): Promise<LiveSession> {
  const result = await requestJson<{ session: LiveSession }>(
    `/api/chat/session/${liveSessionId}/new-chat`,
    {
      method: "POST",
      body: JSON.stringify({ profile_id: profileId }),
    },
  );
  return result.session;
}

export async function setChatSessionProfile(
  liveSessionId: string,
  profileId: string | null,
): Promise<LiveSession> {
  const result = await requestJson<{ session: LiveSession }>(
    `/api/chat/session/${liveSessionId}/profile`,
    {
      method: "PUT",
      body: JSON.stringify({ profile_id: profileId }),
    },
  );
  return result.session;
}

export async function fetchTasks(): Promise<TaskRecord[]> {
  const result = await requestJson<{ tasks: TaskRecord[] }>("/api/tasks");
  return result.tasks;
}

export async function fetchBoardStages(): Promise<BoardStage[]> {
  const result = await requestJson<{ board_stages: BoardStage[] }>("/api/board/stages");
  return result.board_stages;
}

export async function updateBoardStages(
  payload: {
    board_stages: Array<{
      id?: string | null;
      name: string;
      profile_id?: string | null;
      mode_id?: string | null;
      auto_start?: boolean;
    }>;
  },
): Promise<BoardStage[]> {
  const result = await requestJson<{ board_stages: BoardStage[] }>("/api/board/stages", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return result.board_stages;
}

export async function createTask(
  payload: Partial<TaskRecord> & {
    title: string;
    prompt: string;
    profile_id?: string | null;
  },
): Promise<TaskRecord> {
  const result = await requestJson<{ task: TaskRecord }>("/api/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return result.task;
}

export async function updateTask(
  taskId: string,
  payload: Partial<TaskRecord>,
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

export async function createProvider(
  payload: {
    id?: string | null;
    name: string;
    kind: string;
    api_key?: string | null;
    api_key_env?: string | null;
    responses_url?: string | null;
    generic_api_url?: string | null;
  },
  configRevision: string,
): Promise<{ provider: ProviderView; config_revision: string }> {
  return requestJson("/api/config/providers", {
    method: "POST",
    headers: { "If-Match": configRevision },
    body: JSON.stringify(payload),
  });
}

export async function updateProvider(
  providerId: string,
  payload: Partial<{
    name: string | null;
    kind: string | null;
    api_key: string | null;
    api_key_env: string | null;
    responses_url: string | null;
    generic_api_url: string | null;
  }>,
  configRevision: string,
): Promise<{ provider: ProviderView; config_revision: string }> {
  return requestJson(`/api/config/providers/${providerId}`, {
    method: "PATCH",
    headers: { "If-Match": configRevision },
    body: JSON.stringify(payload),
  });
}

export async function deleteProvider(
  providerId: string,
  configRevision: string,
): Promise<void> {
  await requestJson(`/api/config/providers/${providerId}`, {
    method: "DELETE",
    headers: { "If-Match": configRevision },
  });
}

export async function createModelProfile(
  payload: {
    id?: string | null;
    name: string;
    provider_id: string;
    model?: string | null;
    sub_agent_model?: string | null;
    reasoning_effort?: string | null;
    max_tokens?: number | null;
    service_tier?: string | null;
    web_search?: boolean | null;
    max_tool_workers?: number | null;
    max_retries?: number | null;
    compact_threshold?: number | null;
  },
  configRevision: string,
): Promise<{ model_profile: ModelProfileView; config_revision: string }> {
  return requestJson("/api/config/model-profiles", {
    method: "POST",
    headers: { "If-Match": configRevision },
    body: JSON.stringify(payload),
  });
}

export async function updateModelProfile(
  modelProfileId: string,
  payload: Partial<{
    name: string | null;
    provider_id: string | null;
    model: string | null;
    sub_agent_model: string | null;
    reasoning_effort: string | null;
    max_tokens: number | null;
    service_tier: string | null;
    web_search: boolean | null;
    max_tool_workers: number | null;
    max_retries: number | null;
    compact_threshold: number | null;
  }>,
  configRevision: string,
): Promise<{ model_profile: ModelProfileView; config_revision: string }> {
  return requestJson(`/api/config/model-profiles/${modelProfileId}`, {
    method: "PATCH",
    headers: { "If-Match": configRevision },
    body: JSON.stringify(payload),
  });
}

export async function deleteModelProfile(
  modelProfileId: string,
  configRevision: string,
): Promise<void> {
  await requestJson(`/api/config/model-profiles/${modelProfileId}`, {
    method: "DELETE",
    headers: { "If-Match": configRevision },
  });
}

export async function setActiveModelProfile(
  modelProfileId: string | null,
  configRevision: string,
): Promise<{ active_profile_id: string | null; config_revision: string }> {
  return requestJson("/api/config/active-model-profile", {
    method: "PUT",
    headers: { "If-Match": configRevision },
    body: JSON.stringify({ profile_id: modelProfileId }),
  });
}
