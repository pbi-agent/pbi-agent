---
title: 'Custom System Prompt'
description: 'Replace the built-in agent system prompt with INSTRUCTIONS.md.'
---

# Custom System Prompt

Placing an `INSTRUCTIONS.md` file in your workspace root replaces the built-in
system prompt with your own content.

```text
my-project/
├── INSTRUCTIONS.md   ← replaces the built-in system prompt
├── AGENTS.md         ← optional project rules, appended on top
└── ...
```

**When `INSTRUCTIONS.md` is present:**

- Its content becomes the agent's system prompt verbatim.
- Built-in tools such as `shell`, `apply_patch`, `explore_workspace`,
  `read_web_url`, `web_search`, and `sub_agent` remain available unless tool
  visibility is limited by a model profile, command, sub-agent, or
  `pbi-agent run` flag.
- [`AGENTS.md`](/customization/project-rules) project rules are still appended
  if present.

**Example — Python coding agent:**

```markdown
# INSTRUCTIONS.md
You are a Python expert coding agent. You help users write, review, debug, and refactor Python code.

<coding_rules>
- Follow PEP 8 and PEP 257 conventions.
- Use type hints for all function signatures.
- Prefer `pathlib.Path` over `os.path` for file system operations.
</coding_rules>
```

::: tip
`INSTRUCTIONS.md` is the right place for persona and capability definitions that
apply to the whole workspace. Keep it focused — one clear role description with
a small set of non-negotiable rules.
:::

::: warning
Removing `INSTRUCTIONS.md` or leaving it empty restores the default built-in
prompt automatically. The file is re-read at each agent startup; in a live
session, run [`/reload`](/customization/reload) to apply the change before the
next model request.
:::

See [File constraints](/customization/file-constraints) for size, encoding, and
unreadable-file behavior.
