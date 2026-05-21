---
title: 'Built-in Tools'
description: 'The provider-agnostic function tools available to the pbi-agent runtime.'
---

# Built-in Tools

Most built-in tools are exposed through the shared tool registry across providers. Image files are read through `read_file` on providers that support multimodal image input in this build.

Project-local MCP servers are discovered from `.agents/mcp.json` and their tools are merged into the same runtime catalog at startup. Those tools are exposed to the model as ordinary function tools with per-server namespacing, so a tool named `say_hi` from the `echo` server is sent to the model as `echo__say_hi`.

## Availability controls

All built-in tools are enabled by default. Saved model profiles, `pbi-agent run`,
project command frontmatter, and project sub-agent frontmatter can replace that
default with an allow-list.

In the browser app, edit a model profile in **Settings → Model Profiles** and
use **Tool visibility** to select these same groups for that profile.

The allow-list accepts only these built-in tool groups:

| Tool group | Built-ins |
| --- | --- |
| `read` | `read_file`, `search_workspace` |
| `write` | `apply_patch`, `replace_in_file`, `write_file` |
| `web` | `read_web_url` and provider-native web search |
| `sub-agent` | `sub_agent` |
| `shell` | `shell` |

If `allowed_tools` is omitted, all built-ins remain available. If it is present,
only those groups are advertised and executable. MCP and extension tools are not
affected. Provider-specific edit-tool filtering still applies: V4A
providers use `apply_patch`, while other providers use `write_file` and
`replace_in_file`.

The `ask_user` clarification tool is UI-only. It is enabled by the browser
session's interactive mode and is not configurable through model profiles,
command/sub-agent frontmatter, or `pbi-agent run` tool allow-lists.

The `web` group controls both `read_web_url` and native provider web search.
Omit `web` from `allowed_tools` to disable both.

Examples:

```bash
pbi-agent run --prompt "Inspect only" \
  --allowed-tools read

pbi-agent run --prompt "Fetch docs" \
  --allowed-tools read,web,shell

pbi-agent config profiles create --name ReadOnly --provider-id openai \
  --allowed-tools read,web
```

Project command or sub-agent frontmatter uses the same comma-separated key:

```yaml
---
name: review
description: Review without writing files.
allowed_tools: read,shell
---
```

Precedence is replacement-based: command frontmatter, sub-agent frontmatter, or
`pbi-agent run` CLI flags replace the selected profile's tool allow-list for
that turn/run. When absent, the selected profile settings apply.

| Tool | Destructive | Purpose |
| --- | --- | --- |
| `shell` | yes | Run a shell command in the workspace and return stdout, stderr, and exit code. |
| `apply_patch` | yes | Create, update, or delete files through a V4A diff-style file operation. |
| `sub_agent` | no | Delegate a scoped task to a child agent, optionally selecting a discovered project sub-agent type and inheriting parent context. |
| `read_file` | no | Read text files with optional line ranges, summarize tabular files, extract text from PDF and DOCX files, and attach supported image files to the model context. |
| `search_workspace` | no | Search workspace content or paths with compact raw-text results. |
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
| `timeout_ms` | `integer` | no | Timeout in milliseconds. Defaults to `30000`; values above `300000` are capped. |

```json
{
  "command": "uv run pytest -q tests/test_cli.py",
  "working_directory": ".",
  "timeout_ms": 60000
}
```

::: danger
`shell` is marked destructive because it can run write-capable commands. The implementation confines `working_directory` to the workspace tree, but it does not try to sanitize the command itself.
:::

## `apply_patch`

Apply one file operation at a time with a V4A diff payload. For create/update
operations, a standard unified diff for the same single file is accepted as a
fallback and converted internally to V4A.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `operation_type` | `string` | yes | One of `create_file`, `update_file`, or `delete_file`. |
| `path` | `string` | yes | Relative path, or absolute path that still resolves within the workspace root. |
| `diff` | `string` | for create/update | Required for `create_file` and `update_file`; omitted for `delete_file`. |

Do not add a leading blank line to V4A diff bodies unless the target file really
contains that blank line in the matched context. If a V4A body accidentally
starts with a blank line, the tool retries once after stripping leading blank
lines and otherwise returns a targeted hint.

Create-file V4A body:

```text
+hello
+world
```

Update-file V4A body:

```text
 hello
-world
+there
```

Unified diff fallback for an update:

```diff
--- a/notes.txt
+++ b/notes.txt
@@ -1,2 +1,2 @@
 hello
-world
+there
```

::: warning
The `apply_patch` tool still performs one declared operation on one path per
call. It does not accept a full `*** Begin Patch` multi-file envelope. Inside
`pbi-agent`, it is a provider-agnostic function tool backed by
`pbi_agent.tools.apply_diff`.
:::

Tool output is capped to a bounded result that preserves both the beginning and end of long output while marking omitted content.

## `sub_agent`

Delegate a focused task to a child agent that runs with the same provider and tool catalog as the parent session.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `task_instruction` | `string` | yes | The delegated task and the context the child agent needs. |
| `include_context` | `boolean` | no | When `true`, the child inherits the parent conversation context when the provider supports it directly, or via transcript replay otherwise. Defaults to `false`. |
| `agent_type` | `string` | no | Optional project sub-agent name discovered from `.agents/agents/*.md`. Use `default` or omit the field for the built-in generalist child agent. |

```json
{
  "task_instruction": "Review the recent CLI parser changes and summarize any risks.",
  "include_context": true,
  "agent_type": "code-reviewer"
}
```

Runtime behavior:

- Child runs are isolated by default. Set `include_context` to `true` to inherit parent context.
- The child uses `PBI_AGENT_SUB_AGENT_MODEL` or `--sub-agent-model` by default. Project sub-agent files do not override model or reasoning settings.
- The child inherits the parent provider and tool catalog, but `sub_agent` itself is disabled inside the child, so nested sub-agent calls fail fast.
- OpenAI and Google reuse the parent conversation checkpoint when available; other providers fall back to replaying the visible parent transcript plus the current live user turn.
- Unknown `agent_type` values are rejected before the child session starts.
- The child session is bounded to `100` provider requests or `1200` elapsed seconds, whichever happens first.

## `search_workspace`

Search workspace file contents, paths, or both. The tool wraps `codetool-search` and returns its raw token-compressed text output directly to the model, without JSON wrapping on successful searches. Search failures are reported as failed tool calls (`ok: false`).

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `pattern` | `string` | yes | Text or regex pattern to find. |
| `root` | `string` or `string[]` | no | Directory/file path or list of paths to search, relative to the workspace root. Defaults to `.`. |
| `regex` | `boolean` | no | Treat `pattern` as a regular expression. Defaults to `false`; set `true` for regex search. |
| `target` | `content`, `path`, or `both` | no | Search file contents, relative paths, or both. Defaults to `content`. Use `content` or `path` when mixed `both` output would be ambiguous. |
| `path_scope` | `path` or `basename` | no | For path search, match the full relative path or only file basenames. Defaults to `path`. |
| `glob` | `string` or `string[]` | no | Include only files matching the glob or globs. |
| `exclude` | `string` or `string[]` | no | Exclude files matching the glob or globs. |
| `mode` | `files`, `snippets`, or `count` | no | Result detail level. `files` lists matching files/paths, `snippets` includes per-match context, and `count` reports per-file match counts. Defaults to `snippets` when `context_lines > 0`; otherwise `files`. |
| `context_lines` | `integer` | no | Nearby lines to include before and after each snippet match. Defaults to `0`; capped at `20`. |
| `limit` | `integer` | no | Maximum matches to return. Defaults to `50`; capped at `1000`. |
| `cursor` | `integer` or `string` | no | Cursor or result offset from a previous search response for the next page. |

```json
{
  "pattern": "UserService",
  "regex": false,
  "glob": "*.py",
  "limit": 20
}
```

Continue from a previous page:

```json
{
  "pattern": "UserService",
  "regex": false,
  "glob": "*.py",
  "limit": 20,
  "cursor": 20
}
```

::: tip
Use `target: "path"` and `mode: "files"` as a token-compact `find`/recursive `ls` replacement. To list files under a root, use `pattern: ".*"` with `regex: true`; results are files only, without directory metadata or empty directories. Use `mode: "snippets"` with `context_lines` when nearby code is needed. The tool intentionally does not expose backend, case, or result-format controls.
:::

List files recursively under a directory:

```json
{
  "pattern": ".*",
  "root": "src",
  "target": "path",
  "regex": true,
  "mode": "files",
  "limit": 1000
}
```

Raw output format:

- `No Match` means no result.
- `-- more: cursor=N` means repeat the search with that `cursor` for the next page.
- `files` mode returns matching file paths.
- `count` mode returns `path xN`, where `N` is the match count.
- `snippets` mode returns `path:line:text` or groups lines under file headings. Match lines use `line:text`; context lines are plain indented lines.

## `read_file`

Read workspace files safely, with line-range support for text files, compact summaries for tabular files, extraction for formats such as PDF and DOCX, and native multimodal attachment for supported image files.

`read_file` is also the activation path for project-local `SKILL.md` files discovered from `.agents/skills/`. When the prompt catalog lists a skill, the model should load that `SKILL.md` with `read_file` first, then inspect any referenced project-local resources with `read_file` or bounded shell commands.

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

Supported image formats are `.png`, `.jpg`, `.jpeg`, and `.webp`. For those files, `read_file` returns a compact metadata summary to the transcript and keeps the image payload in provider-native multimodal content blocks instead of embedding it into plain text.

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
