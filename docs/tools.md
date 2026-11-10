---
title: 'Built-in Tools'
description: 'The provider-agnostic function tools available to the pbi-agent runtime.'
---

# Built-in Tools

Most built-in tools are exposed through the shared tool registry across providers. Text files are read and searched through `shell` (`cat`, `sed -n`, `rg`, `find`, ...). Image files are attached through `read_image` on providers that support multimodal image input.

Project-local MCP servers are discovered from `.agents/mcp.json` and their tools are merged into the same runtime catalog at startup. Those tools are exposed to the model as ordinary function tools with per-server namespacing, so a tool named `say_hi` from the `echo` server is sent to the model as `echo__say_hi`.

## Availability controls

All built-in tools are enabled by default. Saved model profiles, `pbi-agent run`,
project command frontmatter, and project sub-agent frontmatter can replace that
default with an allow-list.

In the browser app, edit a model profile in **Settings → Model Profiles** and
use **Tool visibility** to select these same groups for that profile.

The allow-list accepts these built-in tool groups:

| Tool group | Built-ins |
| --- | --- |
| `read-image` | `read_image` |
| `write` | `apply_patch`, `replace_in_file`, `write_file` |
| `web` | `read_web_url`, `web_search` |
| `sub-agent` | `sub_agent` |
| `shell` | `shell` |

If `allowed_tools` is omitted, all built-ins remain available. If it is present,
only those groups are advertised and executable. MCP and extension tools are not
affected. Provider-specific edit-tool filtering still applies: V4A
providers use `apply_patch`, while other providers use `write_file` and
`replace_in_file`.

The `ask_user` clarification tool is UI-only. It is enabled by the browser
session's interactive mode by default. Project command frontmatter may also
declare the `ask-user` group in `allowed_tools` to make it available for that command
turn. It is not configurable through model profiles, sub-agent frontmatter, or
`pbi-agent run` tool allow-lists.

The `web` group controls both `read_web_url` and Firecrawl-backed `web_search`.
Omit `web` from `allowed_tools` to disable both.

Examples:

```bash
pbi-agent run --prompt "Inspect only" \
  --allowed-tools shell

pbi-agent run --prompt "Fetch docs" \
  --allowed-tools read-image,web,shell

pbi-agent config profiles create --name ReadOnly --provider-id openai \
  --allowed-tools read-image,web
```

Project command or sub-agent frontmatter uses the same comma-separated key.
Project commands may additionally include `ask-user`:

```yaml
---
name: review
description: Review without writing files.
allowed_tools: read-image,shell
---
```

Precedence is replacement-based: command frontmatter, sub-agent frontmatter, or
`pbi-agent run` CLI flags replace the selected profile's tool allow-list for
that turn/run. When absent, the selected profile settings apply.

Command and sub-agent frontmatter can also scope composition lists. A command
with `sub_agents: confidence-checker` exposes only that project agent through
the `sub_agent` tool for the command turn and requires `agent_type`; the
built-in `default` child agent is not exposed in that scoped mode. A sub-agent
with `sub_agents: fixer` can delegate only to that nested project agent, subject
to the same tool visibility rules and the nested depth cap.

| Tool | Destructive | Purpose |
| --- | --- | --- |
| `shell` | yes | Run a shell command in the workspace and return stdout, stderr, and exit code. |
| `apply_patch` | yes | Create, update, or delete files through a V4A diff-style file operation. |
| `sub_agent` | no | Delegate a scoped task to a child agent, optionally selecting a discovered project sub-agent type and inheriting parent context. |
| `read_image` | no | Attach a supported image file to the model context. |
| `read_web_url` | no | Fetch a public web page through Firecrawl scrape, falling back to markdown.new, and return Markdown. |
| `web_search` | no | Search the public web through Firecrawl and return source results. |

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

Delegate a focused task to a child agent. The built-in `default` child uses the
parent provider/runtime with the configured sub-agent model. A project sub-agent
can set `model_profile_id` and `allowed_tools` in `.agents/agents/*.md` to
override the child runtime and built-in tool visibility for that delegated run.

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
- The default child uses `PBI_AGENT_SUB_AGENT_MODEL` or `--sub-agent-model` by default.
- A project sub-agent with `model_profile_id` uses that saved profile for the child run. Without it, the child inherits the parent runtime and switches to the configured sub-agent model.
- A project sub-agent with `allowed_tools` replaces the inherited/profile built-in tool allow-list for the child run. Without it, the effective parent/profile tool visibility applies.
- The child inherits the parent tool catalog, but `sub_agent` itself is disabled inside the child, so nested sub-agent calls fail fast even if `sub-agent` is included in `allowed_tools`.
- OpenAI and Google reuse the parent conversation checkpoint when available; other providers fall back to replaying the visible parent transcript plus the current live user turn.
- Unknown `agent_type` values are rejected before the child session starts.
- The child session is bounded to `400` provider requests or `1800` elapsed seconds, whichever happens first.

See [Project Sub-agents](/customization/sub-agents#sub-agent-tool-visibility)
for sub-agent `allowed_tools` frontmatter.

## `read_image`

Attach one image file to the model context. Use `shell` for text files.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `path` | `string` | yes | Image file path, workspace-relative or absolute. Paths outside the workspace are allowed. |

```json
{
  "path": "docs/screenshot.png"
}
```

Supported formats are PNG, JPEG, WEBP, HEIC, and HEIF (detected from file content, 20 MB limit). The tool returns compact metadata (`path`, `mime_type`, `byte_count`) to the transcript and keeps the image payload in provider-native multimodal content blocks instead of embedding it into plain text.

## `read_web_url`

Fetch a public web page through Firecrawl scrape and return bounded Markdown
content. If Firecrawl fails, is rate limited, or returns no usable Markdown,
the tool falls back to `markdown.new`.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `url` | `string` | yes | Absolute `http` or `https` URL to convert. |

```json
{
  "url": "https://example.com"
}
```

## `web_search`

Search the public web through Firecrawl and return bounded source results.

| Parameter | Type | Required | Notes |
| --- | --- | --- | --- |
| `query` | `string` | yes | Search query. |
| `limit` | `integer` | no | Result limit. Defaults to `5`; values above `10` are capped. |

```json
{
  "query": "btc live price",
  "limit": 5
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
