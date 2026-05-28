---
title: 'Project Skills'
description: 'Install project-local Agent Skills and expose them to the runtime prompt.'
---

# Project Skills

`pbi-agent` discovers project-local Agent Skills and advertises them to the
model through the system prompt.

## Manage skills from the web UI

Open **Settings → Project → Skills**. The add dialog can browse the official
catalog or install from a GitHub owner/repo, GitHub URL/tree URL, or server-side
local path.

New sessions see installed skills immediately. Active sessions can run
[`/reload`](/customization/reload) before the next model request.

## Manage skills from the CLI

```bash
pbi-agent skills add
pbi-agent skills add --skill openai-docs
pbi-agent skills add ./skills/local-skill
pbi-agent skills add owner/private-repo --skill repo-review
```

Omitting `source` uses the official `pbi-agent/skills` catalog from
`https://github.com/pbi-agent/skills` and lists the available entries. Explicit
multi-skill sources still require `--skill <name>` when installing.

## Local file layout

Supported roots:

- `.agents/skills/<skill-name>/SKILL.md`

Each `SKILL.md` must include YAML frontmatter with at least:

```yaml
---
name: repo-skill
description: Use this skill when the task matches this repository-specific workflow.
---
```

At runtime, discovered skills are appended to the active system prompt as an
`<available_skills>` catalog with the absolute `SKILL.md` path. The model is
expected to load a relevant skill itself with `explore_workspace` using
`target: "read"` before proceeding, then use `explore_workspace` or bounded
shell commands to inspect referenced project-local resources as needed.

Project commands and sub-agents can restrict this catalog with a `skills`
frontmatter field:

```yaml
skills: fastapi,shadcn
```

When a scoped component references a missing or disabled skill, `pbi-agent`
prints a warning and omits that skill from the prompt catalog. If no `skills`
field is present, the normal enabled project skill catalog is used.

This implementation is project-only. User-level skill directories are
intentionally not scanned, and any files referenced by a project skill must stay
inside the workspace so the existing file tools can access them safely.
