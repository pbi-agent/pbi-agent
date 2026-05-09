import type {
  AgentInstallRequest,
  ApiJsonBody,
  ApiJsonRequestBodies,
  ApiOperation,
  ApiOperationPathParams,
  ApiOperationQueryParams,
  ApiPathParams,
  ApiQueryParams,
  ApiResponse,
  CommandInstallRequest,
  CreateSessionRequest,
  LiveSessionInputRequest,
  LiveSessionShellCommandRequest,
  SkillInstallRequest,
  SubmitQuestionResponseRequest,
  UpdateSessionRequest,
} from "./api-types.generated";
import type {
  AllRunsPayload,
  AgentCandidatesPayload,
  AgentInstallPayload,
  AgentListPayload,
  BoardStage,
  BootstrapPayload,
  CommandCandidatesPayload,
  CommandInstallPayload,
  CommandListPayload,
  ConfigBootstrapPayload,
  DashboardStatsPayload,
  ExpandedSessionInput,
  FileMentionItem,
  ImageAttachment,
  LiveSession,
  UserQuestionAnswer,
  MaintenanceConfig,
  ModelProfileView,
  ObservabilityEvent,
  ProviderAuthFlowResponse,
  ProviderAuthLogoutResponse,
  ProviderAuthResponse,
  ProviderModelListPayload,
  ProviderUsageLimitsResponse,
  ProviderView,
  RunSession,
  SessionDetailPayload,
  SessionRecord,
  SkillCandidatesPayload,
  SkillInstallPayload,
  SkillListPayload,
  SlashCommandItem,
  TaskRecord,
} from "./types";

type SessionListResponsePayload = { sessions: SessionRecord[] };
type SessionResponsePayload = { session: SessionRecord };
type LiveSessionResponsePayload = { session: LiveSession };
type FileMentionSearchResponsePayload = { items: FileMentionItem[] };
type SlashCommandSearchResponsePayload = { items: SlashCommandItem[] };
type ImageUploadResponsePayload = { uploads: ImageAttachment[] };
type BoardStagesResponsePayload = { board_stages: BoardStage[] };
type TaskListResponsePayload = { tasks: TaskRecord[] };
type TaskResponsePayload = { task: TaskRecord };
type ProviderResponsePayload = { provider: ProviderView; config_revision: string };
type ModelProfileResponsePayload = {
  model_profile: ModelProfileView;
  config_revision: string;
};
type ActiveModelProfileResponsePayload = {
  active_profile_id: string | null;
  config_revision: string;
};
type MaintenanceConfigResponsePayload = {
  maintenance: MaintenanceConfig;
  config_revision: string;
};
type SessionRunsResponsePayload = { runs: RunSession[] };
type RunDetailResponsePayload = {
  run: RunSession;
  events: ObservabilityEvent[];
};
type DashboardStatsQuery = ApiQueryParams<"GET /api/dashboard/stats"> & {
  scope?: "workspace" | "global";
};
type AllRunsQuery = ApiQueryParams<"GET /api/runs"> & {
  scope?: "workspace" | "global";
};

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

async function apiRequest<
  Operation extends ApiOperation,
  Result extends ApiResponse<Operation> = ApiResponse<Operation>,
>(operation: Operation, path: string, init?: RequestInit): Promise<Result> {
  void operation;
  return requestJson<Result>(path, init);
}

function jsonBody<Operation extends keyof ApiJsonRequestBodies>(
  operation: Operation,
  payload: ApiJsonBody<Operation>,
): string {
  void operation;
  return JSON.stringify(payload);
}

function queryString<Operation extends keyof ApiOperationQueryParams>(
  operation: Operation,
  params: ApiQueryParams<Operation>,
): string {
  void operation;
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value == null) continue;
    if (Array.isArray(value)) {
      for (const item of value) query.append(name, String(item));
    } else {
      query.set(name, String(value));
    }
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

function pathFor<Operation extends keyof ApiOperationPathParams>(
  operation: Operation,
  params: ApiPathParams<Operation>,
): string {
  const separator = operation.indexOf(" ");
  let path = operation.slice(separator + 1);
  for (const [name, value] of Object.entries(params)) {
    path = path.split(`{${name}}`).join(encodeURIComponent(String(value)));
  }
  return path;
}

export function eventStreamUrl(path: string): string {
  return `${window.location.origin}${path}`;
}

export async function fetchBootstrap(): Promise<BootstrapPayload> {
  return apiRequest<"GET /api/bootstrap", BootstrapPayload>(
    "GET /api/bootstrap",
    "/api/bootstrap",
  );
}

export async function fetchConfigBootstrap(): Promise<ConfigBootstrapPayload> {
  return apiRequest<"GET /api/config/bootstrap", ConfigBootstrapPayload>(
    "GET /api/config/bootstrap",
    "/api/config/bootstrap",
  );
}

export async function fetchCommands(): Promise<CommandListPayload> {
  return apiRequest<"GET /api/config/commands", CommandListPayload>(
    "GET /api/config/commands",
    "/api/config/commands",
  );
}

export async function fetchCommandCandidates(
  source?: string | null,
): Promise<CommandCandidatesPayload> {
  return apiRequest<
    "POST /api/config/commands/candidates",
    CommandCandidatesPayload
  >("POST /api/config/commands/candidates", "/api/config/commands/candidates", {
    method: "POST",
    body: jsonBody(
      "POST /api/config/commands/candidates",
      source === undefined ? {} : { source },
    ),
  });
}

export async function installCommand(
  payload: CommandInstallRequest,
): Promise<CommandInstallPayload> {
  return apiRequest<
    "POST /api/config/commands/install",
    CommandInstallPayload
  >("POST /api/config/commands/install", "/api/config/commands/install", {
    method: "POST",
    body: jsonBody("POST /api/config/commands/install", payload),
  });
}

export async function fetchSkills(): Promise<SkillListPayload> {
  return apiRequest<"GET /api/config/skills", SkillListPayload>(
    "GET /api/config/skills",
    "/api/config/skills",
  );
}

export async function fetchSkillCandidates(
  source?: string | null,
): Promise<SkillCandidatesPayload> {
  return apiRequest<
    "POST /api/config/skills/candidates",
    SkillCandidatesPayload
  >("POST /api/config/skills/candidates", "/api/config/skills/candidates", {
    method: "POST",
    body: jsonBody(
      "POST /api/config/skills/candidates",
      source === undefined ? {} : { source },
    ),
  });
}

export async function installSkill(
  payload: SkillInstallRequest,
): Promise<SkillInstallPayload> {
  return apiRequest<
    "POST /api/config/skills/install",
    SkillInstallPayload
  >("POST /api/config/skills/install", "/api/config/skills/install", {
    method: "POST",
    body: jsonBody("POST /api/config/skills/install", payload),
  });
}

export async function fetchAgents(): Promise<AgentListPayload> {
  return apiRequest<"GET /api/config/agents", AgentListPayload>(
    "GET /api/config/agents",
    "/api/config/agents",
  );
}

export async function fetchAgentCandidates(
  source?: string | null,
): Promise<AgentCandidatesPayload> {
  return apiRequest<
    "POST /api/config/agents/candidates",
    AgentCandidatesPayload
  >("POST /api/config/agents/candidates", "/api/config/agents/candidates", {
    method: "POST",
    body: jsonBody(
      "POST /api/config/agents/candidates",
      source === undefined ? {} : { source },
    ),
  });
}

export async function installAgent(
  payload: AgentInstallRequest,
): Promise<AgentInstallPayload> {
  return apiRequest<
    "POST /api/config/agents/install",
    AgentInstallPayload
  >("POST /api/config/agents/install", "/api/config/agents/install", {
    method: "POST",
    body: jsonBody("POST /api/config/agents/install", payload),
  });
}

export async function fetchSessions(): Promise<SessionRecord[]> {
  const result = await apiRequest<
    "GET /api/sessions",
    SessionListResponsePayload
  >("GET /api/sessions", "/api/sessions");
  return result.sessions;
}

export async function updateSession(
  sessionId: string,
  payload: UpdateSessionRequest,
): Promise<SessionRecord> {
  const result = await apiRequest<
    "PATCH /api/sessions/{session_id}",
    SessionResponsePayload
  >(
    "PATCH /api/sessions/{session_id}",
    pathFor("PATCH /api/sessions/{session_id}", { session_id: sessionId }),
    {
      method: "PATCH",
      body: jsonBody("PATCH /api/sessions/{session_id}", payload),
    },
  );
  return result.session;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiRequest<"DELETE /api/sessions/{session_id}">(
    "DELETE /api/sessions/{session_id}",
    pathFor("DELETE /api/sessions/{session_id}", { session_id: sessionId }),
    { method: "DELETE" },
  );
}

export async function fetchSessionDetail(sessionId: string): Promise<SessionDetailPayload> {
  return apiRequest<"GET /api/sessions/{session_id}", SessionDetailPayload>(
    "GET /api/sessions/{session_id}",
    pathFor("GET /api/sessions/{session_id}", { session_id: sessionId }),
  );
}

export async function searchFileMentions(
  query: string,
  limit = 8,
): Promise<FileMentionItem[]> {
  const params = queryString("GET /api/files/search", {
    q: query,
    limit,
  });
  const result = await apiRequest<
    "GET /api/files/search",
    FileMentionSearchResponsePayload
  >(
    "GET /api/files/search",
    `/api/files/search${params}`,
  );
  return result.items;
}

export async function searchSlashCommands(
  query: string,
  limit = 8,
): Promise<SlashCommandItem[]> {
  const params = queryString("GET /api/slash-commands/search", {
    q: query,
    limit,
  });
  const result = await apiRequest<
    "GET /api/slash-commands/search",
    SlashCommandSearchResponsePayload
  >(
    "GET /api/slash-commands/search",
    `/api/slash-commands/search${params}`,
  );
  return result.items;
}

export async function createLiveSession(
  payload: Partial<{
    live_session_id: string;
    session_id: string;
    resume_session_id: string;
    profile_id: string | null;
  }> = {},
): Promise<LiveSession> {
  const created = await createSession({
    profile_id: payload.profile_id ?? null,
  });
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/runs",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/runs",
    pathFor("POST /api/sessions/{session_id}/runs", {
      session_id: created.session_id,
    }),
    {
      method: "POST",
      body: jsonBody("POST /api/sessions/{session_id}/runs", { text: "" }),
    },
  );
  return result.session;
}

export async function createSession(
  payload: CreateSessionRequest = {},
): Promise<SessionRecord> {
  const result = await apiRequest<"POST /api/sessions", SessionResponsePayload>(
    "POST /api/sessions",
    "/api/sessions",
    {
      method: "POST",
      body: jsonBody("POST /api/sessions", payload),
    },
  );
  return result.session;
}

export async function submitQuestionResponse(
  sessionId: string,
  payload: SubmitQuestionResponseRequest & { answers: UserQuestionAnswer[] },
): Promise<LiveSession> {
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/question-response",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/question-response",
    pathFor("POST /api/sessions/{session_id}/question-response", {
      session_id: sessionId,
    }),
    {
      method: "POST",
      body: jsonBody(
        "POST /api/sessions/{session_id}/question-response",
        payload,
      ),
    },
  );
  return result.session;
}

export async function submitSessionQuestionResponse(
  sessionId: string,
  payload: SubmitQuestionResponseRequest & { answers: UserQuestionAnswer[] },
): Promise<LiveSession> {
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/question-response",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/question-response",
    pathFor("POST /api/sessions/{session_id}/question-response", {
      session_id: sessionId,
    }),
    {
      method: "POST",
      body: jsonBody(
        "POST /api/sessions/{session_id}/question-response",
        payload,
      ),
    },
  );
  return result.session;
}

export type SessionInputPayload = LiveSessionInputRequest & {
  text: string;
  file_paths: string[];
  image_paths: string[];
  image_upload_ids: string[];
  profile_id?: string | null;
  interactive_mode?: boolean;
};

export async function submitSessionInput(
  sessionId: string,
  payload: SessionInputPayload,
): Promise<LiveSession> {
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/messages",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/messages",
    pathFor("POST /api/sessions/{session_id}/messages", {
      session_id: sessionId,
    }),
    {
      method: "POST",
      body: jsonBody("POST /api/sessions/{session_id}/messages", payload),
    },
  );
  return result.session;
}

export async function sendSessionMessage(
  sessionId: string,
  payload: SessionInputPayload,
): Promise<LiveSession> {
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/messages",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/messages",
    pathFor("POST /api/sessions/{session_id}/messages", {
      session_id: sessionId,
    }),
    {
      method: "POST",
      body: jsonBody("POST /api/sessions/{session_id}/messages", payload),
    },
  );
  return result.session;
}

export async function runShellCommand(
  sessionId: string,
  payload: LiveSessionShellCommandRequest & { command: string },
): Promise<LiveSession> {
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/shell-command",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/shell-command",
    pathFor("POST /api/sessions/{session_id}/shell-command", {
      session_id: sessionId,
    }),
    {
      method: "POST",
      body: jsonBody("POST /api/sessions/{session_id}/shell-command", payload),
    },
  );
  return result.session;
}

export async function runSessionShellCommand(
  sessionId: string,
  payload: LiveSessionShellCommandRequest & { command: string },
): Promise<LiveSession> {
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/shell-command",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/shell-command",
    pathFor("POST /api/sessions/{session_id}/shell-command", {
      session_id: sessionId,
    }),
    {
      method: "POST",
      body: jsonBody("POST /api/sessions/{session_id}/shell-command", payload),
    },
  );
  return result.session;
}

export async function interruptLiveSession(
  sessionId: string,
): Promise<LiveSession> {
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/interrupt",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/interrupt",
    pathFor("POST /api/sessions/{session_id}/interrupt", {
      session_id: sessionId,
    }),
    { method: "POST" },
  );
  return result.session;
}

export async function interruptSession(sessionId: string): Promise<LiveSession> {
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/interrupt",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/interrupt",
    pathFor("POST /api/sessions/{session_id}/interrupt", {
      session_id: sessionId,
    }),
    { method: "POST" },
  );
  return result.session;
}

export async function uploadTaskImages(files: File[]): Promise<ImageAttachment[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const result = await apiRequest<
    "POST /api/tasks/images",
    ImageUploadResponsePayload
  >("POST /api/tasks/images", "/api/tasks/images", {
    method: "POST",
    body: formData,
  });
  return result.uploads;
}

export async function uploadSessionImages(
  sessionId: string,
  files: File[],
): Promise<ImageAttachment[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/images",
    ImageUploadResponsePayload
  >(
    "POST /api/sessions/{session_id}/images",
    pathFor("POST /api/sessions/{session_id}/images", {
      session_id: sessionId,
    }),
    {
      method: "POST",
      body: formData,
    },
  );
  return result.uploads;
}

export async function uploadSavedSessionImages(
  sessionId: string,
  files: File[],
): Promise<ImageAttachment[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/images",
    ImageUploadResponsePayload
  >(
    "POST /api/sessions/{session_id}/images",
    pathFor("POST /api/sessions/{session_id}/images", {
      session_id: sessionId,
    }),
    {
      method: "POST",
      body: formData,
    },
  );
  return result.uploads;
}

export async function expandSessionInput(text: string): Promise<ExpandedSessionInput> {
  return apiRequest<"POST /api/sessions/expand-input", ExpandedSessionInput>(
    "POST /api/sessions/expand-input",
    "/api/sessions/expand-input",
    {
      method: "POST",
      body: jsonBody("POST /api/sessions/expand-input", { text }),
    },
  );
}

export async function requestNewSession(
  sessionId: string,
  profileId: string | null = null,
): Promise<LiveSession> {
  const result = await apiRequest<
    "POST /api/sessions/{session_id}/new-session",
    LiveSessionResponsePayload
  >(
    "POST /api/sessions/{session_id}/new-session",
    pathFor("POST /api/sessions/{session_id}/new-session", {
      session_id: sessionId,
    }),
    {
      method: "POST",
      body: jsonBody("POST /api/sessions/{session_id}/new-session", {
        profile_id: profileId,
      }),
    },
  );
  return result.session;
}

export async function setLiveSessionProfile(
  sessionId: string,
  profileId: string | null,
): Promise<LiveSession> {
  const result = await apiRequest<
    "PUT /api/sessions/{session_id}/profile",
    LiveSessionResponsePayload
  >(
    "PUT /api/sessions/{session_id}/profile",
    pathFor("PUT /api/sessions/{session_id}/profile", {
      session_id: sessionId,
    }),
    {
      method: "PUT",
      body: jsonBody("PUT /api/sessions/{session_id}/profile", {
        profile_id: profileId,
      }),
    },
  );
  return result.session;
}

export async function setSessionProfile(
  sessionId: string,
  profileId: string | null,
): Promise<LiveSession> {
  const result = await apiRequest<
    "PUT /api/sessions/{session_id}/profile",
    LiveSessionResponsePayload
  >(
    "PUT /api/sessions/{session_id}/profile",
    pathFor("PUT /api/sessions/{session_id}/profile", {
      session_id: sessionId,
    }),
    {
      method: "PUT",
      body: jsonBody("PUT /api/sessions/{session_id}/profile", {
        profile_id: profileId,
      }),
    },
  );
  return result.session;
}

export async function fetchTasks(): Promise<TaskRecord[]> {
  const result = await apiRequest<"GET /api/tasks", TaskListResponsePayload>(
    "GET /api/tasks",
    "/api/tasks",
  );
  return result.tasks;
}

export async function fetchBoardStages(): Promise<BoardStage[]> {
  const result = await apiRequest<
    "GET /api/board/stages",
    BoardStagesResponsePayload
  >("GET /api/board/stages", "/api/board/stages");
  return result.board_stages;
}

export async function updateBoardStages(
  payload: {
    board_stages: Array<{
      id?: string | null;
      name: string;
      profile_id?: string | null;
      command_id?: string | null;
      auto_start?: boolean;
    }>;
  },
): Promise<BoardStage[]> {
  const result = await apiRequest<
    "PUT /api/board/stages",
    BoardStagesResponsePayload
  >("PUT /api/board/stages", "/api/board/stages", {
    method: "PUT",
    body: jsonBody("PUT /api/board/stages", payload),
  });
  return result.board_stages;
}

type TaskWritePayload = Partial<TaskRecord> & {
  title?: string;
  prompt?: string;
  profile_id?: string | null;
  image_upload_ids?: string[];
};

export async function createTask(
  payload: TaskWritePayload & {
    title: string;
    prompt: string;
  },
): Promise<TaskRecord> {
  const result = await apiRequest<"POST /api/tasks", TaskResponsePayload>(
    "POST /api/tasks",
    "/api/tasks",
    {
      method: "POST",
      body: jsonBody("POST /api/tasks", payload),
    },
  );
  return result.task;
}

export async function updateTask(
  taskId: string,
  payload: TaskWritePayload,
): Promise<TaskRecord> {
  const result = await apiRequest<
    "PATCH /api/tasks/{task_id}",
    TaskResponsePayload
  >(
    "PATCH /api/tasks/{task_id}",
    pathFor("PATCH /api/tasks/{task_id}", { task_id: taskId }),
    {
      method: "PATCH",
      body: jsonBody("PATCH /api/tasks/{task_id}", payload),
    },
  );
  return result.task;
}

export async function deleteTask(taskId: string): Promise<void> {
  await apiRequest<"DELETE /api/tasks/{task_id}">(
    "DELETE /api/tasks/{task_id}",
    pathFor("DELETE /api/tasks/{task_id}", { task_id: taskId }),
    { method: "DELETE" },
  );
}

export async function runTask(taskId: string): Promise<TaskRecord> {
  const result = await apiRequest<
    "POST /api/tasks/{task_id}/run",
    TaskResponsePayload
  >(
    "POST /api/tasks/{task_id}/run",
    pathFor("POST /api/tasks/{task_id}/run", { task_id: taskId }),
    { method: "POST" },
  );
  return result.task;
}

export async function createProvider(
  payload: {
    id?: string | null;
    name: string;
    kind: string;
    auth_mode?: string | null;
    api_key?: string | null;
    api_key_env?: string | null;
    responses_url?: string | null;
    generic_api_url?: string | null;
  },
  configRevision: string,
): Promise<{ provider: ProviderView; config_revision: string }> {
  return apiRequest<
    "POST /api/config/providers",
    ProviderResponsePayload
  >(
    "POST /api/config/providers",
    "/api/config/providers",
    {
      method: "POST",
      headers: { "If-Match": configRevision },
      body: jsonBody("POST /api/config/providers", payload),
    },
  );
}

export async function updateProvider(
  providerId: string,
  payload: Partial<{
    name: string | null;
    kind: string | null;
    auth_mode: string | null;
    api_key: string | null;
    api_key_env: string | null;
    responses_url: string | null;
    generic_api_url: string | null;
  }>,
  configRevision: string,
): Promise<{ provider: ProviderView; config_revision: string }> {
  return apiRequest<
    "PATCH /api/config/providers/{provider_id}",
    ProviderResponsePayload
  >(
    "PATCH /api/config/providers/{provider_id}",
    pathFor("PATCH /api/config/providers/{provider_id}", {
      provider_id: providerId,
    }),
    {
      method: "PATCH",
      headers: { "If-Match": configRevision },
      body: jsonBody("PATCH /api/config/providers/{provider_id}", payload),
    },
  );
}

export async function deleteProvider(
  providerId: string,
  configRevision: string,
): Promise<void> {
  await apiRequest<"DELETE /api/config/providers/{provider_id}">(
    "DELETE /api/config/providers/{provider_id}",
    pathFor("DELETE /api/config/providers/{provider_id}", {
      provider_id: providerId,
    }),
    {
      method: "DELETE",
      headers: { "If-Match": configRevision },
    },
  );
}

export async function fetchProviderModels(
  providerId: string,
): Promise<ProviderModelListPayload> {
  return apiRequest<
    "GET /api/config/providers/{provider_id}/models",
    ProviderModelListPayload
  >(
    "GET /api/config/providers/{provider_id}/models",
    pathFor("GET /api/config/providers/{provider_id}/models", {
      provider_id: providerId,
    }),
  );
}

export async function fetchProviderAuthStatus(
  providerId: string,
): Promise<ProviderAuthResponse> {
  return apiRequest<
    "GET /api/provider-auth/{provider_id}",
    ProviderAuthResponse
  >(
    "GET /api/provider-auth/{provider_id}",
    pathFor("GET /api/provider-auth/{provider_id}", {
      provider_id: providerId,
    }),
  );
}

export async function startProviderAuthFlow(
  providerId: string,
  method: "browser" | "device",
): Promise<ProviderAuthFlowResponse> {
  return apiRequest<
    "POST /api/provider-auth/{provider_id}/flows",
    ProviderAuthFlowResponse
  >(
    "POST /api/provider-auth/{provider_id}/flows",
    pathFor("POST /api/provider-auth/{provider_id}/flows", {
      provider_id: providerId,
    }),
    {
      method: "POST",
      body: jsonBody("POST /api/provider-auth/{provider_id}/flows", { method }),
    },
  );
}

export async function fetchProviderAuthFlow(
  providerId: string,
  flowId: string,
): Promise<ProviderAuthFlowResponse> {
  return apiRequest<
    "GET /api/provider-auth/{provider_id}/flows/{flow_id}",
    ProviderAuthFlowResponse
  >(
    "GET /api/provider-auth/{provider_id}/flows/{flow_id}",
    pathFor("GET /api/provider-auth/{provider_id}/flows/{flow_id}", {
      provider_id: providerId,
      flow_id: flowId,
    }),
  );
}

export async function pollProviderAuthFlow(
  providerId: string,
  flowId: string,
): Promise<ProviderAuthFlowResponse> {
  return apiRequest<
    "POST /api/provider-auth/{provider_id}/flows/{flow_id}/poll",
    ProviderAuthFlowResponse
  >(
    "POST /api/provider-auth/{provider_id}/flows/{flow_id}/poll",
    pathFor("POST /api/provider-auth/{provider_id}/flows/{flow_id}/poll", {
      provider_id: providerId,
      flow_id: flowId,
    }),
    { method: "POST" },
  );
}

export async function refreshProviderAuth(
  providerId: string,
): Promise<ProviderAuthResponse> {
  return apiRequest<
    "POST /api/provider-auth/{provider_id}/refresh",
    ProviderAuthResponse
  >(
    "POST /api/provider-auth/{provider_id}/refresh",
    pathFor("POST /api/provider-auth/{provider_id}/refresh", {
      provider_id: providerId,
    }),
    { method: "POST" },
  );
}

export async function logoutProviderAuth(
  providerId: string,
): Promise<ProviderAuthLogoutResponse> {
  return apiRequest<
    "DELETE /api/provider-auth/{provider_id}",
    ProviderAuthLogoutResponse
  >(
    "DELETE /api/provider-auth/{provider_id}",
    pathFor("DELETE /api/provider-auth/{provider_id}", {
      provider_id: providerId,
    }),
    { method: "DELETE" },
  );
}

export async function fetchProviderUsageLimits(
  providerId: string,
): Promise<ProviderUsageLimitsResponse> {
  return apiRequest<
    "GET /api/provider-auth/{provider_id}/usage-limits",
    ProviderUsageLimitsResponse
  >(
    "GET /api/provider-auth/{provider_id}/usage-limits",
    pathFor("GET /api/provider-auth/{provider_id}/usage-limits", {
      provider_id: providerId,
    }),
  );
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
    compact_tail_turns?: number | null;
    compact_preserve_recent_tokens?: number | null;
    compact_tool_output_max_chars?: number | null;
  },
  configRevision: string,
): Promise<{ model_profile: ModelProfileView; config_revision: string }> {
  return apiRequest<
    "POST /api/config/model-profiles",
    ModelProfileResponsePayload
  >(
    "POST /api/config/model-profiles",
    "/api/config/model-profiles",
    {
      method: "POST",
      headers: { "If-Match": configRevision },
      body: jsonBody("POST /api/config/model-profiles", payload),
    },
  );
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
    compact_tail_turns: number | null;
    compact_preserve_recent_tokens: number | null;
    compact_tool_output_max_chars: number | null;
  }>,
  configRevision: string,
): Promise<{ model_profile: ModelProfileView; config_revision: string }> {
  return apiRequest<
    "PATCH /api/config/model-profiles/{profile_id}",
    ModelProfileResponsePayload
  >(
    "PATCH /api/config/model-profiles/{profile_id}",
    pathFor("PATCH /api/config/model-profiles/{profile_id}", {
      profile_id: modelProfileId,
    }),
    {
      method: "PATCH",
      headers: { "If-Match": configRevision },
      body: jsonBody(
        "PATCH /api/config/model-profiles/{profile_id}",
        payload,
      ),
    },
  );
}

export async function deleteModelProfile(
  modelProfileId: string,
  configRevision: string,
): Promise<void> {
  await apiRequest<"DELETE /api/config/model-profiles/{profile_id}">(
    "DELETE /api/config/model-profiles/{profile_id}",
    pathFor("DELETE /api/config/model-profiles/{profile_id}", {
      profile_id: modelProfileId,
    }),
    {
      method: "DELETE",
      headers: { "If-Match": configRevision },
    },
  );
}

export async function setActiveModelProfile(
  modelProfileId: string | null,
  configRevision: string,
): Promise<{ active_profile_id: string | null; config_revision: string }> {
  return apiRequest<
    "PUT /api/config/active-model-profile",
    ActiveModelProfileResponsePayload
  >(
    "PUT /api/config/active-model-profile",
    "/api/config/active-model-profile",
    {
      method: "PUT",
      headers: { "If-Match": configRevision },
      body: jsonBody("PUT /api/config/active-model-profile", {
        profile_id: modelProfileId,
      }),
    },
  );
}

export async function updateMaintenanceConfig(
  retentionDays: number,
  configRevision: string,
): Promise<{ maintenance: MaintenanceConfig; config_revision: string }> {
  return apiRequest<
    "PUT /api/config/maintenance",
    MaintenanceConfigResponsePayload
  >(
    "PUT /api/config/maintenance",
    "/api/config/maintenance",
    {
      method: "PUT",
      headers: { "If-Match": configRevision },
      body: jsonBody("PUT /api/config/maintenance", {
        retention_days: retentionDays,
      }),
    },
  );
}

export async function fetchSessionRuns(sessionId: string): Promise<RunSession[]> {
  const result = await apiRequest<
    "GET /api/sessions/{session_id}/runs",
    SessionRunsResponsePayload
  >(
    "GET /api/sessions/{session_id}/runs",
    pathFor("GET /api/sessions/{session_id}/runs", {
      session_id: sessionId,
    }),
  );
  return result.runs;
}

export async function fetchRunDetail(
  runSessionId: string,
  scope?: "workspace" | "global",
): Promise<{ run: RunSession; events: ObservabilityEvent[] }> {
  const qs = queryString("GET /api/runs/{run_session_id}", { scope });
  return apiRequest<
    "GET /api/runs/{run_session_id}",
    RunDetailResponsePayload
  >(
    "GET /api/runs/{run_session_id}",
    `${pathFor("GET /api/runs/{run_session_id}", {
      run_session_id: runSessionId,
    })}${qs}`,
  );
}

export async function fetchDashboardStats(
  params: DashboardStatsQuery,
): Promise<DashboardStatsPayload> {
  const qs = queryString("GET /api/dashboard/stats", params);
  return apiRequest<"GET /api/dashboard/stats", DashboardStatsPayload>(
    "GET /api/dashboard/stats",
    `/api/dashboard/stats${qs}`,
  );
}

export async function fetchAllRuns(params: AllRunsQuery): Promise<AllRunsPayload> {
  const qs = queryString("GET /api/runs", params);
  return apiRequest<"GET /api/runs", AllRunsPayload>(
    "GET /api/runs",
    `/api/runs${qs}`,
  );
}
