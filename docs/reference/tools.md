---
title: 'Built-in Tools'
description: 'The provider-agnostic function tools available to the pbi-agent runtime.'
layout: doc
outline: [2, 3]
---

# Built-in Tools

All providers expose the same built-in tools through the shared tool registry.

| Tool | Destructive | Purpose |
| --- | --- | --- |
| `shell` | yes | Run a shell command in the workspace and return stdout, stderr, and exit code. |
| `python_exec` | yes | Run trusted local Python code with the same interpreter/environment as the CLI, including `polars`, `pypdf`, and `python-docx`, and optionally capture a structured `result`. |
| `apply_patch` | yes | Create, update, or delete files through a V4A diff-style file operation. |
| `skill_knowledge` | no | Load bundled Power BI skill markdown from the local knowledge base. |
| `init_report` | no | Scaffold the bundled PBIP template into a destination directory. |
| `list_files` | no | List files and directories in the workspace, with optional glob and type filtering. |
| `search_files` | no | Search text file contents for a string or regex pattern. |
| `read_file` | no | Read text files with optional line ranges, summarize tabular files, and extract text from PDF and DOCX files. |
| `read_web_url` | no | Fetch a public web page through markdown.new and return Markdown. |

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

Execute trusted local Python snippets in a subprocess using the same Python interpreter and environment variables as the CLI process. This includes installed libraries such as `polars` for data manipulation and `pypdf` plus `python-docx` for PDF or DOCX analysis.

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
`python_exec` is trusted local execution, not a sandbox. Executed code can read and write files the CLI can access, import installed packages from the active Python environment, including `polars`, `pypdf`, and `python-docx`, and make any Python standard-library or package calls available to that interpreter. The subprocess boundary is for runtime stability and timeout enforcement, not for security isolation.
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
