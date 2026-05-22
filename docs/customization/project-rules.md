---
title: 'Project Rules'
description: 'Add repository-specific conventions with AGENTS.md.'
---

# Project Rules

`AGENTS.md` adds project-specific rules on top of whatever system prompt is
active: the default built-in prompt, or your custom
[`INSTRUCTIONS.md`](/customization/instructions).

Use it for conventions, constraints, or context that is specific to the current
repository or workspace.

```text
my-project/
├── AGENTS.md   ← injected as <project_rules> in every session
└── ...
```

The file contents are wrapped in `<project_rules>` tags and appended to the
system prompt:

```xml
<project_rules>
... your AGENTS.md content ...
</project_rules>
```

**Example — repository conventions:**

```markdown
# AGENTS.md
- All Python files must pass `ruff check` before committing.
- Use `uv run pytest` to execute tests; never use bare `pytest`.
- Keep internal data in `~/.pbi-agent/`, never in the workspace root.
```

::: tip
`AGENTS.md` is checked into version control alongside your project. It is the
right place for team conventions that every contributor and every agent session
should follow.
:::

See [File constraints](/customization/file-constraints) for size, encoding, and
unreadable-file behavior.
