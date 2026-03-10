---
title: 'Built-in Tools'
description: 'The four provider-agnostic function tools available to the pbi-agent runtime.'
layout: doc
outline: [2, 3]
---

# Built-in Tools

All providers expose the same four built-in tools through the shared tool registry.

| Tool | Destructive | Purpose |
| --- | --- | --- |
| `shell` | yes | Run a shell command in the workspace and return stdout, stderr, and exit code. |
| `apply_patch` | yes | Create, update, or delete files through a V4A diff-style file operation. |
| `skill_knowledge` | no | Load bundled Power BI skill markdown from the local knowledge base. |
| `init_report` | no | Scaffold the bundled PBIP template into a destination directory. |

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
