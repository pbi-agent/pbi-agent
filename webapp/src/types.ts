export type SessionRecord = {
  session_id: string;
  directory: string;
  provider: string;
  model: string;
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
  stage: "backlog" | "plan" | "processing" | "review";
  position: number;
  project_dir: string;
  session_id: string | null;
  run_status: "idle" | "running" | "completed" | "failed";
  last_result_summary: string;
  created_at: string;
  updated_at: string;
  last_run_started_at: string | null;
  last_run_finished_at: string | null;
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

export type LiveSession = {
  live_session_id: string;
  resume_session_id: string | null;
  created_at: string;
  status: "starting" | "running" | "ended";
  exit_code: number | null;
  fatal_error: string | null;
  ended_at: string | null;
};

export type FileMentionItem = {
  path: string;
  kind: "file" | "image";
};

export type SlashCommandItem = {
  name: string;
  description: string;
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
  provider: string;
  model: string;
  reasoning_effort: string;
  supports_image_inputs: boolean;
  sessions: SessionRecord[];
  tasks: TaskRecord[];
  live_sessions: LiveSession[];
  board_stages: string[];
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
