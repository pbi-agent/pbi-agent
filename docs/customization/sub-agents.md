---
title: 'Project Sub-agents'
description: 'Define project-local specialist child agents for the sub_agent tool.'
---

# Project Sub-agents

`pbi-agent` can discover project-local sub-agent definitions and advertise them
to the main agent as specialized delegated worker choices for the `sub_agent`
tool.

## Manage agents from the web UI

Open **Settings → Project → Agents**. The add dialog follows the same workflow
as skills and commands: browse the official catalog, or install from a GitHub
owner/repo, GitHub URL/tree URL, or server-side local path.

New sessions see installed agents immediately. Active sessions can run
[`/reload`](/customization/reload) before the next model request.

## Manage agents from the CLI

```bash
pbi-agent agents add
pbi-agent agents add --agent code-reviewer
pbi-agent agents add ./agents/local
pbi-agent agents add owner/private-repo --agent repo-reviewer
```

Omitting `source` uses the official `pbi-agent/agents` catalog from
`https://github.com/pbi-agent/agents` and lists the available entries. Explicit
multi-agent sources still require `--agent <name>` when installing.

## Local file layout

Supported root:

- `.agents/agents/<agent-name>.md`

Each sub-agent file must include YAML frontmatter with at least `name` and
`description`. It may also include:

- `model_profile_id` to use a specific saved profile whenever that sub-agent
  runs.
- `allowed_tools` to replace the parent/profile built-in tool visibility for
  that child run.
- `skills` to limit the child agent's skill catalog to a comma-separated list
  of project skill names.
- `commands` to include comma-separated project command bodies as reusable
  prompt components inside the child system prompt.
- `sub_agents` to allow nested delegation only to a comma-separated list of
  project sub-agent names.

```yaml
---
name: reviewer
description: Review implementation and test coverage.
model_profile_id: reviewer
allowed_tools: read,shell
skills: fastapi,shadcn
commands: review
sub_agents: confidence-checker,fixer
---
```

The Markdown body becomes that sub-agent's system prompt. It can be minimal, or
even empty, when the agent is primarily composed from `commands`. When
`model_profile_id` is omitted, project sub-agents inherit the parent runtime and
use the profile's configured `sub_agent_model` when present, falling back to the
parent model.

Supported frontmatter in this implementation is intentionally narrow:

- Scalar `key: value` pairs for `name`, `description`, optional
  `model_profile_id`, `allowed_tools`, `skills`, `commands`, and `sub_agents`
- Quoted strings
- `|` and `>` block scalars
- Blank lines and `#` comments

Nested mappings, lists, anchors, and other general YAML features are rejected
and the file is skipped with a warning on stderr.

Frontmatter list fields use comma-separated scalar values only, not YAML arrays.

## Runtime behavior

At runtime, discovered sub-agents are appended to the active system prompt as an
`<available_sub_agents>` catalog. The main agent can then call `sub_agent` with
`agent_type` set to the discovered `name`. Calling `sub_agent` without
`agent_type` still uses the built-in generalist child agent unless the active
command or child agent has declared a scoped `sub_agents` list.

Project sub-agents:

- Run in isolated child-agent contexts by default. Set `include_context: true`
  on the `sub_agent` tool call to inherit the parent conversation context.
- Use the same provider as the parent session unless their frontmatter sets
  `model_profile_id`.
- Can delegate to a nested sub-agent only when their frontmatter sets a scoped
  `sub_agents` list and the child runtime has the `sub-agent` tool group
  available. Nested delegation is capped at depth 2, and an agent cannot list
  itself as a nested sub-agent.

You can inspect the discovered catalog without starting a model request:

- CLI: `pbi-agent --agents`
- Session UI: `/agents`

## Sub-agent tool visibility

`allowed_tools` uses the same comma-separated built-in tool groups as model
profiles, `pbi-agent run`, and project commands:

| Tool group | Built-ins |
| --- | --- |
| `read` | `explore_workspace` |
| `write` | `apply_patch`, `replace_in_file`, `write_file` |
| `web` | `read_web_url` and provider-native web search |
| `sub-agent` | `sub_agent` |
| `shell` | `shell` |

If `allowed_tools` is omitted, the child run inherits the effective tool
visibility from its selected runtime. If a sub-agent sets `model_profile_id`,
that profile's tool visibility applies unless the parent turn explicitly
overrode tool visibility.

If `allowed_tools` is present in the sub-agent frontmatter, it replaces the
inherited/profile allow-list for that child run only. This is useful for
specialists such as read-only reviewers:

```yaml
---
name: readonly-reviewer
description: Review changes without editing files or running shell commands.
allowed_tools: read
---
```

Including `sub-agent` in a child allow-list does not enable recursive
delegation by itself. The sub-agent must also declare a scoped `sub_agents`
list. MCP and extension tools are not affected by this allow-list, and the
UI-only `ask_user` tool is not configurable through sub-agent frontmatter.

See [Built-in Tools](/tools#availability-controls) for full availability
semantics and precedence.

## Scoped skills, command components, and nested agents

Sub-agent frontmatter can compose other project components:

```yaml
---
name: reviewer
description: Review changes against the plan.
model_profile_id: reviewer
allowed_tools: read
commands: review
---
```

`commands` resolves project commands by name, normalized id, or slash alias such
as `review` or `/review`. Referenced command bodies are appended to the child
system prompt as prompt components after the sub-agent body, in the listed
order. Command frontmatter metadata is not inherited by the child: the
sub-agent's own `model_profile_id`, `allowed_tools`, `skills`, and `sub_agents`
remain the runtime policy.

`skills` works like command skill scoping. When omitted, the child sees the
normal enabled project skill catalog. When present, only the listed skills are
advertised. Missing or disabled skills are soft references: `pbi-agent` prints a
CLI warning and omits them. Skill loading requires the child to have the `read`
tool group so it can load `SKILL.md` with `explore_workspace`.

`sub_agents` enables controlled nested delegation. When omitted, nested
`sub_agent` calls are disabled inside the child. When present, only the listed
enabled project agents are exposed to that child, the nested tool schema
requires `agent_type`, and the built-in `default` child agent is not exposed at
that nested level. Missing or disabled configured sub-agents, unknown
`commands`, and self-references are strict runtime configuration errors.
