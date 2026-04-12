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
  runtime_summary: RuntimeSummary;
};

export type RuntimeSummary = {
  provider: string | null;
  provider_id: string | null;
  profile_id: string | null;
  model: string | null;
  reasoning_effort: string | null;
};

export type BoardStage = {
  id: string;
  name: string;
  position: number;
  profile_id: string | null;
  mode_id: string | null;
  auto_start: boolean;
};

export type UsagePayload = {
  input_tokens: number;
  cached_input_tokens: number;
  cache_write_tokens: number;
  cache_write_1h_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  tool_use_tokens: number;
  provider_total_tokens: number;
  sub_agent_input_tokens: number;
  sub_agent_output_tokens: number;
  sub_agent_reasoning_tokens: number;
  sub_agent_tool_use_tokens: number;
  sub_agent_provider_total_tokens: number;
  sub_agent_cost_usd: number;
  context_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  main_agent_total_tokens: number;
  sub_agent_total_tokens: number;
  model: string;
  service_tier: string;
};

export type LiveSessionRuntime = {
  provider_id: string | null;
  profile_id: string | null;
  provider: string;
  model: string;
  reasoning_effort: string;
};

export type LiveSession = LiveSessionRuntime & {
  live_session_id: string;
  session_id: string | null;
  task_id: string | null;
  kind: "chat" | "task";
  project_dir: string;
  created_at: string;
  status: "starting" | "running" | "ended";
  exit_code: number | null;
  fatal_error: string | null;
  ended_at: string | null;
  last_event_seq: number;
};

export type HistoryItem = {
  item_id: string;
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
  history_items: HistoryItem[];
  active_live_session: LiveSession | null;
};

export type LiveSessionSnapshot = {
  live_session_id: string;
  session_id: string | null;
  runtime: RuntimeSummary | null;
  input_enabled: boolean;
  wait_message: string | null;
  session_usage: UsagePayload | null;
  turn_usage:
    | { usage: UsagePayload | null; elapsed_seconds?: number | null }
    | null;
  session_ended: boolean;
  fatal_error: string | null;
  items: Record<string, unknown>[];
  sub_agents: Record<string, { title: string; status: string }>;
  last_event_seq: number;
};

export type FileMentionItem = {
  path: string;
  kind: "file" | "image";
};

export type SlashCommandItem = {
  name: string;
  description: string;
  kind: "local_command" | "mode";
};

export type ImageAttachment = {
  upload_id: string;
  name: string;
  mime_type: string;
  byte_count: number;
  preview_url: string;
};

export type ExpandedChatInput = {
  text: string;
  file_paths: string[];
  image_paths: string[];
  warnings: string[];
};

export type BootstrapPayload = {
  workspace_root: string;
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

export type ProviderView = {
  id: string;
  name: string;
  kind: string;
  responses_url: string | null;
  generic_api_url: string | null;
  secret_source: "none" | "plaintext" | "env_var";
  secret_env_var: string | null;
  has_secret: boolean;
};

export type ProviderKindMetadata = {
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
  is_active_default: boolean;
  resolved_runtime: ResolvedRuntimeView;
};

export type ModeView = {
  id: string;
  name: string;
  slash_alias: string;
  description: string;
  instructions: string;
};

export type ConfigBootstrapPayload = {
  providers: ProviderView[];
  model_profiles: ModelProfileView[];
  modes: ModeView[];
  active_profile_id: string | null;
  config_revision: string;
  options: ConfigOptions;
};

export type TimelineMessageItem = {
  kind: "message";
  itemId: string;
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

export type TimelineToolGroupItem = {
  kind: "tool_group";
  itemId: string;
  label: string;
  items: { text: string; classes?: string }[];
  subAgentId?: string;
};

export type TimelineItem =
  | TimelineMessageItem
  | TimelineThinkingItem
  | TimelineToolGroupItem;

export type WebEvent = {
  seq: number;
  type: string;
  created_at: string;
  payload: Record<string, unknown>;
};
