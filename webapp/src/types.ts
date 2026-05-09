import type {
  AgentCandidateViewModel,
  AgentCandidatesResponse,
  AgentInstallResponse,
  AgentListResponse,
  AgentViewModel,
  AppSseEventModel,
  CommandCandidateViewModel,
  CommandCandidatesResponse,
  CommandInstallResponse,
  CommandListResponse,
  CommandViewModel,
  LiveSessionSnapshotModel,
  ProcessingStateModel,
  RunSessionModel,
  SessionRecordModel,
  SkillCandidateViewModel,
  SkillCandidatesResponse,
  SkillInstallResponse,
  SkillListResponse,
  SkillViewModel,
  SessionSseEventModel,
  SseControlEventModel,
  SseEventModel,
  TokenUsagePayloadModel,
} from "./api-types.generated";

export type SessionLifecycleStatus = NonNullable<SessionRecordModel["status"]>;

export type SessionStatus = SessionLifecycleStatus;

export type RunSessionStatus = RunSessionModel["status"];

export type SessionRecord = {
  session_id: string;
  directory: string;
  provider: string;
  provider_id: string | null;
  model: string;
  profile_id: string | null;
  previous_id: string | null;
  title: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  created_at: string;
  updated_at: string;
  status?: SessionStatus;
  active_run_id?: string | null;
  active_live_session_id?: string | null;
  task_id?: string | null;
};

export type TaskRecord = {
  task_id: string;
  directory: string;
  title: string;
  prompt: string;
  stage: string;
  position: number;
  project_dir: string;
  session_id: string | null;
  profile_id: string | null;
  run_status: "idle" | "running" | "completed" | "failed";
  last_result_summary: string;
  created_at: string;
  updated_at: string;
  last_run_started_at: string | null;
  last_run_finished_at: string | null;
  image_attachments: ImageAttachment[];
  runtime_summary: RuntimeSummary;
};

export type RuntimeSummary = {
  provider: string | null;
  provider_id: string | null;
  profile_id: string | null;
  model: string | null;
  reasoning_effort: string | null;
  compact_threshold?: number | null;
};

export type BoardStage = {
  id: string;
  name: string;
  position: number;
  profile_id: string | null;
  command_id: string | null;
  auto_start: boolean;
};

export type UsagePayload = TokenUsagePayloadModel;

export type SubAgentSnapshot = {
  title: string;
  status: string;
  waitMessage?: string | null;
  wait_message?: string | null;
  processing?: ProcessingState | null;
  session_usage?: UsagePayload | null;
  turn_usage?: {
    usage: UsagePayload | null;
    elapsed_seconds?: number | null;
  } | null;
};

export type LiveSessionRuntime = {
  provider_id: string | null;
  profile_id: string | null;
  provider: string;
  model: string;
  reasoning_effort: string;
  compact_threshold: number;
};

export type LiveSession = LiveSessionRuntime & {
  live_session_id: string;
  session_id: string | null;
  task_id: string | null;
  kind: "session" | "task";
  project_dir: string;
  created_at: string;
  status: SessionStatus;
  exit_code: number | null;
  fatal_error: string | null;
  ended_at: string | null;
  last_event_seq: number;
};

export type PendingUserQuestion = {
  question_id: string;
  question: string;
  suggestions: [string, string, string];
  recommended_suggestion_index: 0;
};

export type PendingUserQuestions = {
  prompt_id: string;
  questions: PendingUserQuestion[];
};

export type UserQuestionAnswer = {
  question_id: string;
  answer: string;
  selected_suggestion_index: 0 | 1 | 2 | null;
  custom: boolean;
};

export type MessagePartIds = {
  content: string;
  file_paths: string[];
  image_attachments: string[];
};

export type HistoryItem = {
  item_id: string;
  message_id: string;
  part_ids: MessagePartIds;
  role: "user" | "assistant" | "notice" | "error" | "debug";
  content: string;
  file_paths: string[];
  image_attachments: ImageAttachment[];
  markdown: boolean;
  historical: boolean;
  created_at: string;
};

export type SessionDetailPayload = {
  session: SessionRecord;
  status?: SessionStatus;
  history_items: HistoryItem[];
  timeline?: LiveSessionSnapshot | null;
  active_live_session: LiveSession | null;
  active_run?: LiveSession | null;
};

export type LiveSessionSnapshot = Omit<
  LiveSessionSnapshotModel,
  | "runtime"
  | "processing"
  | "session_usage"
  | "turn_usage"
  | "pending_user_questions"
  | "sub_agents"
> & {
  runtime: RuntimeSummary | null;
  processing: ProcessingState | null;
  session_usage: UsagePayload | null;
  turn_usage:
    | { usage: UsagePayload | null; elapsed_seconds?: number | null }
    | null;
  pending_user_questions: PendingUserQuestions | null;
  sub_agents: Record<string, SubAgentSnapshot>;
};

export type ProcessingPhase = NonNullable<ProcessingStateModel["phase"]>;

export type ProcessingState = Omit<
  ProcessingStateModel,
  "phase" | "message" | "active_tool_count"
> & {
  phase: ProcessingPhase | null;
  message: string | null;
  active_tool_count?: number;
};

export type FileMentionItem = {
  path: string;
  kind: "file" | "image";
};

export type SlashCommandItem = {
  name: string;
  description: string;
  kind: "local_command" | "command";
};

export type ImageAttachment = {
  upload_id: string;
  name: string;
  mime_type: string;
  byte_count: number;
  preview_url: string;
};

export type ExpandedSessionInput = {
  text: string;
  file_paths: string[];
  image_paths: string[];
  warnings: string[];
};

export type BootstrapPayload = {
  workspace_root: string;
  workspace_key: string;
  workspace_display_path: string;
  is_sandbox: boolean;
  provider: string | null;
  provider_id: string | null;
  profile_id: string | null;
  model: string | null;
  reasoning_effort: string | null;
  supports_image_inputs: boolean;
  sessions: SessionRecord[];
  tasks: TaskRecord[];
  live_sessions: LiveSession[];
  board_stages: BoardStage[];
};

export type ProviderAuthStatus = {
  auth_mode: string;
  backend: string | null;
  session_status: "missing" | "connected" | "expired";
  has_session: boolean;
  can_refresh: boolean;
  account_id: string | null;
  email: string | null;
  plan_type: string | null;
  expires_at: number | null;
};

export type ProviderAuthSession = {
  provider_id: string;
  backend: string;
  expires_at: number | null;
  account_id: string | null;
  email: string | null;
  plan_type: string | null;
};

export type ProviderAuthFlow = {
  flow_id: string;
  provider_id: string;
  backend: string;
  method: "browser" | "device";
  status: "pending" | "completed" | "failed";
  authorization_url: string | null;
  callback_url: string | null;
  verification_url: string | null;
  user_code: string | null;
  interval_seconds: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type ProviderView = {
  id: string;
  name: string;
  kind: string;
  auth_mode: string;
  responses_url: string | null;
  generic_api_url: string | null;
  secret_source: "none" | "plaintext" | "env_var";
  secret_env_var: string | null;
  has_secret: boolean;
  auth_status: ProviderAuthStatus;
};

export type ProviderKindMetadata = {
  label: string;
  description: string | null;
  default_auth_mode: string;
  auth_modes: string[];
  auth_mode_metadata: Record<string, ProviderAuthModeMetadata>;
  default_model: string;
  default_sub_agent_model: string | null;
  default_responses_url: string | null;
  default_generic_api_url: string | null;
  supports_responses_url: boolean;
  supports_generic_api_url: boolean;
  supports_service_tier: boolean;
  supports_native_web_search: boolean;
  supports_image_inputs: boolean;
};

export type ProviderAuthModeMetadata = {
  label: string;
  account_label: string | null;
  supported_methods: Array<"browser" | "device">;
};

export type ProviderAuthResponse = {
  provider: ProviderView;
  auth_status: ProviderAuthStatus;
  session: ProviderAuthSession | null;
};

export type ProviderModelFetchError = {
  code: string;
  message: string;
  status_code: number | null;
};

export type ProviderModelView = {
  id: string;
  display_name: string | null;
  created: number | string | null;
  owned_by: string | null;
  input_modalities: string[];
  output_modalities: string[];
  aliases: string[];
  supports_reasoning_effort: boolean | null;
};

export type ProviderModelListPayload = {
  provider_id: string;
  provider_kind: string;
  discovery_supported: boolean;
  manual_entry_required: boolean;
  models: ProviderModelView[];
  error: ProviderModelFetchError | null;
};

export type ProviderAuthLogoutResponse = {
  provider: ProviderView;
  auth_status: ProviderAuthStatus;
  removed: boolean;
};

export type ProviderAuthFlowResponse = {
  provider: ProviderView;
  auth_status: ProviderAuthStatus;
  flow: ProviderAuthFlow;
  session: ProviderAuthSession | null;
};

export type UsageLimitCredits = {
  has_credits: boolean | null;
  unlimited: boolean | null;
  balance: string | null;
};

export type UsageLimitWindow = {
  name: string;
  used_percent: number | null;
  remaining_percent: number | null;
  window_minutes: number | null;
  resets_at: number | null;
  reset_at_iso: string | null;
  used_requests: number | null;
  total_requests: number | null;
  remaining_requests: number | null;
};

export type UsageLimitBucket = {
  id: string;
  label: string;
  unlimited: boolean;
  overage_allowed: boolean;
  overage_count: number;
  status: "ok" | "warning" | "exhausted" | "unknown";
  credits: UsageLimitCredits | null;
  windows: UsageLimitWindow[];
};

export type ProviderUsageLimitsResponse = {
  provider_id: string;
  provider_kind: string;
  account_label: string | null;
  plan_type: string | null;
  fetched_at: string;
  buckets: UsageLimitBucket[];
};

export type ConfigOptions = {
  provider_kinds: string[];
  reasoning_efforts: string[];
  openai_service_tiers: string[];
  provider_metadata: Record<string, ProviderKindMetadata>;
};

export type ResolvedRuntimeView = {
  provider: string;
  provider_id: string;
  profile_id: string;
  model: string;
  sub_agent_model: string | null;
  reasoning_effort: string;
  max_tokens: number;
  service_tier: string | null;
  web_search: boolean;
  max_tool_workers: number;
  max_retries: number;
  compact_threshold: number;
  compact_tail_turns: number;
  compact_preserve_recent_tokens: number;
  compact_tool_output_max_chars: number;
  responses_url: string;
  generic_api_url: string;
  supports_image_inputs: boolean;
};

export type ModelProfileView = {
  id: string;
  name: string;
  provider_id: string;
  provider: { id: string; name: string; kind: string };
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
  is_active_default: boolean;
  resolved_runtime: ResolvedRuntimeView;
};

export type CommandView = CommandViewModel;

export type CommandCandidateView = CommandCandidateViewModel;

export type CommandListPayload = CommandListResponse;

export type CommandCandidatesPayload = CommandCandidatesResponse;

export type CommandInstallPayload = CommandInstallResponse;

export type SkillView = SkillViewModel;

export type SkillCandidateView = SkillCandidateViewModel;

export type SkillListPayload = SkillListResponse;

export type SkillCandidatesPayload = SkillCandidatesResponse;

export type SkillInstallPayload = SkillInstallResponse;

export type AgentView = AgentViewModel;

export type AgentCandidateView = AgentCandidateViewModel;

export type AgentListPayload = AgentListResponse;

export type AgentCandidatesPayload = AgentCandidatesResponse;

export type AgentInstallPayload = AgentInstallResponse;

export type ConfigBootstrapPayload = {
  providers: ProviderView[];
  model_profiles: ModelProfileView[];
  commands: CommandView[];
  skills: SkillView[];
  agents: AgentView[];
  active_profile_id: string | null;
  maintenance: MaintenanceConfig;
  config_revision: string;
  options: ConfigOptions;
};

export type MaintenanceConfig = {
  retention_days: number;
};

export type TimelineMessageItem = {
  kind: "message";
  itemId: string;
  messageId?: string;
  partIds?: MessagePartIds;
  role: "user" | "assistant" | "notice" | "error" | "debug";
  content: string;
  filePaths?: string[];
  imageAttachments?: ImageAttachment[];
  markdown: boolean;
  subAgentId?: string;
};

export type TimelineThinkingItem = {
  kind: "thinking";
  itemId: string;
  title: string;
  content: string;
  subAgentId?: string;
};

export type ToolCallStatus = "running" | "completed" | "failed";

export type ToolGroupStatus = "running" | "completed";

export type ApplyPatchToolMetadata = {
  tool_name?: string;
  path?: string;
  operation?: string;
  success?: boolean;
  detail?: string;
  diff?: string;
  diff_line_numbers?: Array<{ old: number | null; new: number | null }>;
  call_id?: string;
  status?: ToolCallStatus;
  arguments?: Record<string, unknown> | string | null;
  result?: Record<string, unknown> | string | null;
  error?: unknown;
  command?: string;
  working_directory?: string;
  timeout_ms?: number | string;
  exit_code?: number | null;
  timed_out?: boolean;
};

export type ToolCallMetadata = Omit<
  Record<string, unknown>,
  keyof ApplyPatchToolMetadata
> & ApplyPatchToolMetadata;

export type TimelineToolGroupEntry = {
  text: string;
  classes?: string;
  metadata?: ToolCallMetadata;
};

export type TimelineToolGroupItem = {
  kind: "tool_group";
  itemId: string;
  label: string;
  status?: ToolGroupStatus;
  items: TimelineToolGroupEntry[];
  subAgentId?: string;
};

export type TimelineItem =
  | TimelineMessageItem
  | TimelineThinkingItem
  | TimelineToolGroupItem;

export type WebEvent = SseEventModel;
export type WebEventType = WebEvent["type"];
export type WebEventOf<T extends WebEventType> = Extract<WebEvent, { type: T }>;
export type WebEventPayload<T extends WebEventType> = WebEventOf<T>["payload"];
export type SessionWebEvent = SessionSseEventModel;
export type AppWebEvent = AppSseEventModel;
export type ControlWebEvent = SseControlEventModel;

export type LiveSessionLifecycleEventType =
  | "live_session_started"
  | "live_session_updated"
  | "live_session_bound"
  | "live_session_ended";

export type LiveSessionLifecycleEvent = {
  seq: number;
  type: LiveSessionLifecycleEventType;
  created_at: string;
  live_session: LiveSession;
};

export type RunSession = {
  run_session_id: string;
  session_id: string | null;
  parent_run_session_id: string | null;
  agent_name: string | null;
  agent_type: string | null;
  provider: string | null;
  provider_id: string | null;
  profile_id: string | null;
  model: string | null;
  status: RunSessionStatus;
  started_at: string;
  ended_at: string | null;
  total_duration_ms: number | null;
  input_tokens: number;
  cached_input_tokens: number;
  cache_write_tokens: number;
  cache_write_1h_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  tool_use_tokens: number;
  provider_total_tokens: number;
  estimated_cost_usd: number;
  total_tool_calls: number;
  total_api_calls: number;
  error_count: number;
  kind?: string;
  task_id?: string | null;
  project_dir?: string | null;
  last_event_seq?: number;
  snapshot?: unknown;
  exit_code?: number | null;
  fatal_error?: string | null;
  metadata: unknown;
};

export type ObservabilityEvent = {
  run_session_id: string;
  session_id: string | null;
  step_index: number;
  event_type: string;
  timestamp: string;
  duration_ms: number | null;
  provider: string | null;
  model: string | null;
  url: string | null;
  request_config: unknown;
  request_payload: unknown;
  response_payload: unknown;
  tool_name: string | null;
  tool_call_id: string | null;
  tool_input: unknown;
  tool_output: unknown;
  tool_duration_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  status_code: number | null;
  success: boolean | null;
  error_message: string | null;
  metadata: unknown;
};

// -- Dashboard / Observability Aggregation --------------------------------

export type DailyBucket = {
  date: string;
  runs: number;
  tokens: number;
  cost: number;
  errors: number;
};

export type ProviderBreakdown = {
  provider: string | null;
  model: string | null;
  run_count: number;
  total_tokens: number;
  total_cost: number;
  avg_duration_ms: number | null;
  error_count: number;
  total_api_calls: number;
  total_tool_calls: number;
};

export type DashboardOverview = {
  total_sessions: number;
  total_runs: number;
  total_input_tokens: number;
  total_cached_tokens: number;
  total_output_tokens: number;
  total_reasoning_tokens: number;
  total_cost: number;
  total_api_calls: number;
  total_tool_calls: number;
  total_errors: number;
  avg_duration_ms: number | null;
  completed_runs: number;
  failed_runs: number;
};

export type DashboardStatsPayload = {
  overview: DashboardOverview;
  breakdown: ProviderBreakdown[];
  daily: DailyBucket[];
};

export type AllRunsRun = RunSession & {
  session_title: string | null;
};

export type AllRunsPayload = {
  runs: AllRunsRun[];
  total_count: number;
};
