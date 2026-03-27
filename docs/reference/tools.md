---
title: 'Built-in Tools'
description: 'The provider-agnostic function tools available to the pbi-agent runtime.'
layout: doc
outline: [2, 3]
---

# Built-in Tools

Most built-in tools are exposed through the shared tool registry across providers. `read_image` is only enabled on providers that support multimodal image input in this build.

Project-local MCP servers are discovered from `.agents/mcp.json` and their tools are merged into the same runtime catalog at startup. Those tools are exposed to the model as ordinary function tools with per-server namespacing, so a tool named `say_hi` from the `echo` server is sent to the model as `echo__say_hi`.

| Tool | Destructive | Purpose |
| --- | --- | --- |
| `shell` | yes | Run a shell command in the workspace and return stdout, stderr, and exit code. |
| `python_exec` | yes | Run trusted local Python code with the same interpreter/environment as the CLI, including `pandas`, `pypdf`, and `python-docx`, and optionally capture a structured `result`. |
| `apply_patch` | yes | Create, update, or delete files through a V4A diff-style file operation. |
| `skill_knowledge` | no | Load bundled Power BI skill markdown from the local knowledge base. |
| `init_report` | no | Scaffold the bundled PBIP template into a destination directory. |
| `sub_agent` | no | Delegate a scoped task to a child agent, optionally selecting a discovered project sub-agent type and inheriting parent context. |
| `list_files` | no | List files and directories in the workspace, with optional glob and type filtering. |
| `search_files` | no | Search text file contents for a string or regex pattern. |
| `read_file` | no | Read text files with optional line ranges, summarize tabular files, and extract text from PDF and DOCX files. |
| `read_image` | no | Read a local image file and attach it to the model context in native multimodal format. |
| `read_web_url` | no | Fetch a public web page through markdown.new and return Markdown. |

## MCP Tools

Discovered MCP tools behave like built-in function tools from the model's point of view:

- They are loaded from `.agents/mcp.json` at startup.
- Each server contributes tools after a simple namespaced rename of the form `server__tool`.
- The UI shows a friendly `mcp:server/tool` label when rendering tool activity.
- The runtime skips broken server entries and continues loading the rest.

MCP tools follow the JSON schema advertised by the server during `list_tools()`. They are passed through to the underlying MCP server with the original tool name and arguments.

## `shell`

Execute shell commands within the workspace root by default.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `command` | `string` | yes | Shell command to run. |
| `working_directory` | `string` | no | Relative directory inside the workspace. Absolute paths are only allowed if they stay within the workspace root. |
| `timeout_ms` | `integer` | no | Timeout in milliseconds, capped at `120000`. |

```json
{
  "command": "uv run pytest",
  "working_directory": ".",
  "timeout_ms": 120000
}
```

::: danger
`shell` is marked destructive because it can run write-capable commands. The implementation confines `working_directory` to the workspace tree, but it does not try to sanitize the command itself.
:::

## `apply_patch`

Apply one file operation at a time with a V4A diff payload.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `operation_type` | `string` | yes | One of `create_file`, `update_file`, or `delete_file`. |
| `path` | `string` | yes | Relative path, or absolute path that still resolves within the workspace root. |
| `diff` | `string` | for create/update | Required for `create_file` and `update_file`; omitted for `delete_file`. |

```text
*** Begin Patch
*** Add File: notes.txt
+hello
*** End Patch
```

::: warning
The `apply_patch` tool is different from this coding environment's patch helper. Inside `pbi-agent`, it is a provider-agnostic function tool backed by `pbi_agent.tools.apply_diff`.
:::

Tool output is capped to a bounded result that preserves both the beginning and end of long output while marking omitted content.

## `python_exec`

Execute trusted local Python snippets in a subprocess using the same Python interpreter and environment variables as the CLI process. This includes installed libraries such as `pandas` for data manipulation and `pypdf` plus `python-docx` for PDF or DOCX analysis.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `code` | `string` | yes | Python source code to execute. |
| `working_directory` | `string` | no | Relative directory inside the workspace. Absolute paths are only allowed if they stay within the workspace root. |
| `timeout_seconds` | `integer` | no | Timeout in seconds, capped at `120`. Defaults to `30`. |
| `capture_result` | `boolean` | no | When `true`, return the top-level `result` variable if it is JSON-serializable. |

```json
{
  "code": "result = {'status': 'ok', 'value': 42}",
  "working_directory": ".",
  "timeout_seconds": 30,
  "capture_result": true
}
```

::: danger
`python_exec` is trusted local execution, not a sandbox. Executed code can read and write files the CLI can access, import installed packages from the active Python environment, including `pandas`, `pypdf`, and `python-docx`, and make any Python standard-library or package calls available to that interpreter. The subprocess boundary is for runtime stability and timeout enforcement, not for security isolation.
:::

## `skill_knowledge`

Load Power BI skill markdown from the bundled knowledge base.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `skills` | `string[]` | yes | One or more skill names to retrieve. |

```json
{
  "skills": ["report_structure", "bar_chart_visual"]
}
```

::: details Bundled skill files (15)
`action_button`, `bar_chart_visual`, `card_visual`, `composite_model_entity_query_guardrails`, `csv_local_import`, `filter_propagation`, `navigation_bookmarks`, `report_structure`, `skill_generator`, `slicer_visual`, `table_visual`, `theme_branding`, `tmdl_descriptions`, `tmdl_modeling`, and `visual_container_schema`.
:::

## `init_report`

Programmatically scaffold the bundled PBIP template.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `dest` | `string` | no | Destination directory. Defaults to `"."`. |
| `force` | `boolean` | no | Overwrite existing template files when `true`. Defaults to `false`. |

```json
{
  "dest": ".",
  "force": false
}
```

## `sub_agent`

Delegate a focused task to a child agent that runs with the same provider and tool catalog as the parent session.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `task_instruction` | `string` | yes | The delegated task and the context the child agent needs. |
| `include_context` | `boolean` | no | When `true`, the child inherits the parent conversation context when the provider supports it directly, or via transcript replay otherwise. Defaults to `false`. |
| `agent_type` | `string` | no | Optional project sub-agent name discovered from `.agents/*.md`. Use `default` or omit the field for the built-in generalist child agent. |

```json
{
  "task_instruction": "Review the recent CLI parser changes and summarize any risks.",
  "include_context": true,
  "agent_type": "code-reviewer"
}
```

Runtime behavior:

- Child runs are isolated by default. Set `include_context` to `true` to inherit parent context.
- The child uses `PBI_AGENT_SUB_AGENT_MODEL` or `--sub-agent-model` by default unless the selected project sub-agent overrides `model` in its frontmatter.
- The child inherits the parent provider and tool catalog, but `sub_agent` itself is disabled inside the child, so nested sub-agent calls fail fast.
- OpenAI and Google reuse the parent conversation checkpoint when available; other providers fall back to replaying the visible parent transcript plus the current live user turn.
- Unknown `agent_type` values are rejected before the child session starts.
- The child session is bounded to `50` provider requests or `600` elapsed seconds, whichever happens first.

## `list_files`

List directory contents for general workspace discovery, or narrow results by glob and entry type for targeted lookups. Recursive listings skip common generated and dependency directories such as `.git`, `.venv`, `node_modules`, and caches.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `path` | `string` | no | Directory or file path relative to the workspace root. Defaults to `"."`. |
| `recursive` | `boolean` | no | Traverse subdirectories when `true`. Defaults to `true`. |
| `glob` | `string` | no | Optional glob filter. Match against the entry name unless the pattern includes a path separator. |
| `entry_type` | `string` | no | One of `all`, `file`, or `directory`. Defaults to `all`. |
| `max_entries` | `integer` | no | Maximum number of entries to return. Defaults to `200`. |

```json
{
  "path": ".",
  "recursive": true,
  "glob": "docs/**/*.md",
  "entry_type": "file",
  "max_entries": 50
}
```

## `read_file`

Read workspace files safely, with line-range support for text files, compact summaries for tabular files, and extraction for formats such as PDF and DOCX.

`read_file` is also the activation path for project-local `SKILL.md` files discovered from `.agents/skills/`. When the prompt catalog lists a skill, the model should load that `SKILL.md` with `read_file` first, then inspect any referenced project-local resources with `read_file`, `list_files`, or `search_files`.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `path` | `string` | yes | File path relative to the workspace root, or absolute path that still resolves within the workspace. |
| `start_line` | `integer` | no | 1-based starting line for text files. Defaults to `1`. |
| `max_lines` | `integer` | no | Maximum text lines to return. Defaults to `200`. |
| `encoding` | `string` | no | Text encoding override. Defaults to automatic detection. |

```json
{
  "path": ".agents/skills/repo-skill/SKILL.md",
  "start_line": 1,
  "max_lines": 200
}
```

## `read_image`

Read a local image file and attach it to the model context while returning a compact metadata summary.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `path` | `string` | yes | Image path relative to the workspace root, or an absolute path that still resolves within the workspace. |

```json
{
  "path": "general_ocr_002.png"
}
```

Supported image formats are `.png`, `.jpg`, `.jpeg`, and `.webp`.

`read_image` returns a concise JSON summary to the transcript and keeps the base64 image payload in provider-native multimodal content blocks instead of embedding it into plain text.

::: warning
`read_image` is currently only registered for OpenAI, Google, and Anthropic. It is intentionally hidden for xAI and Generic in this build.
:::

## `read_web_url`

Fetch a public web page through `markdown.new` and return bounded Markdown content.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `url` | `string` | yes | Absolute `http` or `https` URL to convert. |

```json
{
  "url": "https://example.com"
}
```

This v1 wrapper uses `markdown.new` defaults only. It does not yet expose `method` or `retain_images`.

## Parallel Tool Execution

`pbi-agent` executes tool calls through a `ThreadPoolExecutor` when more than one tool call is returned and `--max-tool-workers` is greater than `1`.

| Setting | Effect |
| --- | --- |
| `--max-tool-workers 1` | Force serial tool execution |
| `--max-tool-workers 4` | Default parallel worker count |
| multiple tool calls + workers > 1 | Execute concurrently and return results in call order |

::: tip
Parallelism is runtime-wide, not provider-specific. The provider decides how to represent tool calls, but actual execution happens in the shared tool runtime.
:::
