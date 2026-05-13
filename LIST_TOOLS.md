# Codex Tool List Audit

Source audited: `~/codex`, primarily `codex-rs/core/src/tools/handlers/*_spec.rs`, `codex-rs/tools/src/tool_spec.rs`, and `codex-rs/tools/src/responses_api.rs`.

Notes:
- Availability is feature/model/config dependent; this lists model-facing tool definitions present in the codebase.
- `Function` tools use JSON object parameters with `additionalProperties: false` where specified.
- MCP and dynamic tools can add externally supplied tools at runtime; their names/descriptions/schemas come from the MCP/dynamic tool metadata, not fixed source constants.

## Fixed built-in tools

### `apply_patch`
- Original definition: `create_apply_patch_freeform_tool` (`apply_patch_spec.rs`)
- Kind: custom/freeform tool, grammar format (`type: grammar`, `syntax: lark`)
- Params/input: raw patch text matching `apply_patch.lark`; not JSON.
- Description: `Use the \`apply_patch\` tool to edit files. This is a FREEFORM tool, so do not wrap the patch in JSON.`

### `shell`
- Original definition: `create_shell_tool` (`shell_spec.rs`)
- Params:
  - `command` (array of string, required): The command to execute.
  - `workdir` (string): The working directory to execute the command in.
  - `timeout_ms` (number): The timeout for the command in milliseconds.
  - `sandbox_permissions` (string): sandbox mode/request escalation/additional permissions.
  - `justification` (string): user approval justification when escalation is requested.
  - `prefix_rule` (array of string): suggested future approval prefix rule.
  - `additional_permissions` (object, optional when enabled): `{ network: { enabled }, file_system: { read: string[], write: string[] } }`.
- Description: Runs a shell command and returns its output; on Unix, arguments are passed to `execvp()` and most terminal commands should be prefixed with `["bash", "-lc"]`; always set `workdir`.

### `shell_command`
- Original definition: `create_shell_command_tool` (`shell_spec.rs`)
- Params:
  - `command` (string, required): The shell script to execute in the user's default shell.
  - `workdir` (string): The working directory to execute the command in.
  - `timeout_ms` (number): The timeout for the command in milliseconds.
  - `login` (boolean, optional when login shell allowed): Whether to run with login shell semantics; defaults true.
  - `sandbox_permissions`, `justification`, `prefix_rule`, `additional_permissions`: same approval fields as `shell`.
- Description: Runs a shell command and returns its output; always set `workdir`; avoid `cd` unless necessary.

### `exec_command`
- Original definition: `create_exec_command_tool_with_environment_id` (`shell_spec.rs`)
- Params:
  - `cmd` (string, required): Shell command to execute.
  - `workdir` (string): Optional working directory; defaults to turn cwd.
  - `shell` (string): Shell binary; defaults to user's default shell.
  - `tty` (boolean): Allocate a TTY; defaults false.
  - `yield_time_ms` (number): How long to wait for output before yielding.
  - `max_output_tokens` (number): Maximum tokens to return before truncation.
  - `login` (boolean, optional): Run shell with `-l/-i` semantics; defaults true.
  - `environment_id` (string, optional): target environment id.
  - approval fields: `sandbox_permissions`, `justification`, `prefix_rule`, `additional_permissions`.
- Description: Runs a command in a PTY, returning output or a session ID for ongoing interaction.

### `write_stdin`
- Original definition: `create_write_stdin_tool` (`shell_spec.rs`)
- Params:
  - `session_id` (number, required): running unified exec session id.
  - `chars` (string): bytes to write to stdin, may be empty to poll.
  - `yield_time_ms` (number): wait time before yielding.
  - `max_output_tokens` (number): maximum tokens to return.
- Description: Writes characters to an existing unified exec session and returns recent output.

### `local_shell`
- Original definition: `create_local_shell_tool` / `ToolSpec::LocalShell` (`shell_spec.rs`, `tool_spec.rs`)
- Params/input: no JSON parameters in Codex; serialized as `{ "type": "local_shell" }`.
- Description: no source description field; native Responses API local shell tool.

### `request_permissions`
- Original definition: `create_request_permissions_tool` (`shell_spec.rs`)
- Params:
  - `permissions` (object, required): `{ network: { enabled }, file_system: { read: string[], write: string[] } }`.
  - `reason` (string): Optional short explanation.
- Description: Request additional filesystem or network permissions from the user and wait for grant; grants apply automatically to later shell-like commands in the current turn or session depending on approval scope.

### `update_plan`
- Original definition: `create_update_plan_tool` (`plan_spec.rs`)
- Params:
  - `plan` (array, required): list of `{ step: string, status: string }`; status one of `pending`, `in_progress`, `completed`.
  - `explanation` (string): optional explanation.
- Description: Updates the task plan. At most one step can be `in_progress` at a time.

### `view_image`
- Original definition: `create_view_image_tool` (`view_image_spec.rs`; name from `VIEW_IMAGE_TOOL_NAME`)
- Params:
  - `path` (string, required): local filesystem path to an image file.
  - `detail` (string, optional when enabled): only supported value `original`.
  - `environment_id` (string, optional): selected environment id.
- Description: View a local image from the filesystem; only use if given a full filepath by the user and the image is not already attached in thread context.

### `request_user_input`
- Original definition: `create_request_user_input_tool` (`request_user_input_spec.rs`)
- Params:
  - `questions` (array, required): 1-3 question objects with:
    - `id` (string): stable snake_case identifier.
    - `header` (string): short UI label, 12 or fewer chars.
    - `question` (string): single-sentence prompt.
    - `options` (array): 2-3 choices, each `{ label: string, description: string }`; client adds free-form Other.
- Description: Request user input for one to three short questions and wait for the response; available only in configured modes.

### `spawn_agent`
- Original definitions: `create_spawn_agent_tool_v1`, `create_spawn_agent_tool_v2` (`multi_agents_spec.rs`)
- Params v2:
  - `task_name` (string, required): lowercase/digits/underscores task name.
  - `message` (string, required): task/instruction for new agent.
  - common optional metadata fields include agent type/model/reasoning controls depending on config.
- Params v1: common spawn-agent fields; no required fields in schema.
- Description: Spawn a new agent; spawned agents inherit current model by default; returns agent id/task name plus nickname where available. Exact description includes available model guidance and optional usage hints.

### `send_input`
- Original definition: `create_send_input_tool_v1` (`multi_agents_spec.rs`)
- Params:
  - `target` (string, required): agent id from `spawn_agent`.
  - `message` (string): legacy plain-text message.
  - `items` (array): structured collab input items.
  - `interrupt` (boolean): stop current task and handle immediately when true; otherwise queue.
- Description: Send a message to an existing agent; use `interrupt=true` to redirect work immediately; reuse agents when context-dependent.

### `send_message`
- Original definition: `create_send_message_tool` (`multi_agents_spec.rs`)
- Params: `target` (string, required), `message` (string, required).
- Description: Send a message to an existing agent. The message will be delivered promptly. Does not trigger a new turn.

### `followup_task`
- Original definition: `create_followup_task_tool` (`multi_agents_spec.rs`)
- Params: `target` (string, required), `message` (string, required).
- Description: Send a message to an existing non-root target agent and trigger a turn; queues if target is mid-turn.

### `resume_agent`
- Original definition: `create_resume_agent_tool` (`multi_agents_spec.rs`)
- Params: `id` (string, required): agent id to resume.
- Description: Resume a previously closed agent by id so it can receive `send_input` and `wait_agent` calls.

### `wait_agent`
- Original definitions: `create_wait_agent_tool_v1`, `create_wait_agent_tool_v2` (`multi_agents_spec.rs`)
- Params: timeout/wait options produced by `wait_agent_tool_parameters_v1/v2` (include timeout controls bounded by configured defaults/min/max; v1 targets final statuses, v2 waits for mailbox updates).
- Description v1: Wait for agents to reach a final status; completed statuses may include final message; empty status when timed out.
- Description v2: Wait for a mailbox update from any live agent, including queued messages and final-status notifications; returns summary or timeout.

### `list_agents`
- Original definition: `create_list_agents_tool` (`multi_agents_spec.rs`)
- Params: `path_prefix` (string): optional task-path prefix.
- Description: List live agents in the current root thread tree; optionally filter by task-path prefix.

### `close_agent`
- Original definitions: `create_close_agent_tool_v1`, `create_close_agent_tool_v2` (`multi_agents_spec.rs`)
- Params: `target` (string, required): agent id or canonical task name.
- Description: Close an agent and any open descendants when no longer needed; returns previous status before shutdown request.

### `spawn_agents_on_csv`
- Original definition: `create_spawn_agents_on_csv_tool` (`agent_jobs_spec.rs`)
- Params:
  - `csv_path` (string, required): CSV input path.
  - `instruction` (string, required): template with `{column_name}` placeholders.
  - `id_column` (string): stable item id column.
  - `output_csv_path` (string): output CSV path.
  - `max_concurrency` / `max_workers` (number): concurrency controls.
  - `max_runtime_seconds` (number): worker timeout.
  - `output_schema` (object): expected worker result schema.
- Description: Process a CSV by spawning one worker sub-agent per row; each worker must call `report_agent_job_result`; blocks until all rows finish and exports results.

### `report_agent_job_result`
- Original definition: `create_report_agent_job_result_tool` (`agent_jobs_spec.rs`)
- Params: `job_id` (string, required), `item_id` (string, required), `result` (object, required), `stop` (boolean).
- Description: Worker-only tool to report a result for an agent job item. Main agents should not call this.

### `get_goal`
- Original definition: `create_get_goal_tool` (`goal_spec.rs`)
- Params: empty object.
- Description: Get the current goal for this thread, including status, budgets, token/elapsed usage, and remaining token budget.

### `create_goal`
- Original definition: `create_create_goal_tool` (`goal_spec.rs`)
- Params: `objective` (string, required), `token_budget` (integer, optional).
- Description: Create a goal only when explicitly requested; do not infer goals; fails if a goal exists; set token budget only when requested.

### `update_goal`
- Original definition: `create_update_goal_tool` (`goal_spec.rs`)
- Params: `status` (string enum, required): only `complete`.
- Description: Update existing goal only to mark achieved; use `complete` only when objective is achieved and no required work remains.

### `tool_search`
- Original definition: `create_tool_search_tool` (`tool_search_spec.rs`; serialized as `ToolSpec::ToolSearch`)
- Params: `query` (string, required), `limit` (number).
- Description: Searches deferred tool metadata with BM25 and exposes matching tools for the next model call; for MCP discovery, use this instead of MCP resource listing when available.

### `request_plugin_install`
- Original definition: `create_request_plugin_install_tool` (`request_plugin_install_spec.rs`)
- Params: `tool_type` (string, required: `connector` or `plugin`), `action_type` (string, required: `install`), `tool_id` (string, required), `suggest_reason` (string, required).
- Description: Ask the user to install one known plugin/connector from the configured list, only when explicitly requested and not already available; do not call in parallel.

### `list_mcp_resources`
- Original definition: `create_list_mcp_resources_tool` (`mcp_resource_spec.rs`)
- Params: `server` (string), `cursor` (string).
- Description: Lists resources provided by MCP servers; resources provide model context such as files, database schemas, or app-specific information; prefer resources over web search when possible.

### `list_mcp_resource_templates`
- Original definition: `create_list_mcp_resource_templates_tool` (`mcp_resource_spec.rs`)
- Params: `server` (string), `cursor` (string).
- Description: Lists parameterized resource templates from MCP servers; prefer resource templates over web search when possible.

### `read_mcp_resource`
- Original definition: `create_read_mcp_resource_tool` (`mcp_resource_spec.rs`)
- Params: `server` (string, required), `uri` (string, required).
- Description: Read a specific resource from an MCP server by server name and resource URI.

### `web_search`
- Original definition: `ToolSpec::WebSearch` (`tool_spec.rs`)
- Params/config fields serialized with the tool: `external_web_access` (bool), `filters.allowed_domains` (string[]), `user_location` (`type`, `country`, `region`, `city`, `timezone`), `search_context_size`, `search_content_types`.
- Description: no explicit source description; native Responses API web search tool.

### `image_generation`
- Original definition: `ToolSpec::ImageGeneration` (`tool_spec.rs`)
- Params/config fields: `output_format` (string).
- Description: no explicit source description; native Responses API image generation tool.

### `test_sync_tool`
- Original definition: `create_test_sync_tool` (`test_sync_spec.rs`)
- Params: `sleep_before_ms` (number), `sleep_after_ms` (number), `barrier` object with `id` (string, required), `participants` (number, required), `timeout_ms` (number).
- Description: Internal synchronization helper used by Codex integration tests.

## Runtime/external tool families

### MCP tools
- Original definition path: `mcp_tool_to_responses_api_tool` / `parse_mcp_tool` (`tools/src/responses_api.rs`, `tools/src/mcp_tool.rs`).
- Tool name: supplied by MCP server, possibly renamed under a Codex `ToolName`.
- Params/input: MCP tool `inputSchema`, converted to Codex `JsonSchema`.
- Description: MCP tool description from server metadata, defaulting to empty string.

### Dynamic/loadable tools
- Original definition path: `dynamic_tool_to_responses_api_tool`, `dynamic_tool_to_loadable_tool_spec` (`tools/src/responses_api.rs`).
- Tool name: from `DynamicToolSpec` metadata.
- Params/input: dynamic tool input schema.
- Description: from dynamic tool definition; namespace description defaults to `Tools in the <namespace> namespace.` when no user description exists.

### Namespaces
- Original definition: `ResponsesApiNamespace` / `LoadableToolSpec::Namespace` (`tools/src/responses_api.rs`, `tools/src/tool_spec.rs`).
- Tool name: namespace name.
- Params/input: contains nested function tools, each with its own parameters.
- Description: namespace description; default is `Tools in the <namespace> namespace.`
