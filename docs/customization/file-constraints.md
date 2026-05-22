---
title: 'Customization File Constraints'
description: 'Size, encoding, empty-file, and unreadable-file behavior for prompt files.'
---

# Customization File Constraints

These constraints apply to workspace prompt files such as `INSTRUCTIONS.md` and
`AGENTS.md`:

| Property | Value |
| --- | --- |
| Maximum size | 1 MB; content beyond that is truncated with a warning on stderr. |
| Encoding | UTF-8; invalid bytes are replaced, not rejected. |
| Empty file | Treated as absent, so the default behavior applies. |
| Permissions | Unreadable file emits a warning on stderr and is skipped. |

Project skills, commands, sub-agents, and MCP configs have their own required
file layouts:

- [Project skills](/customization/skills)
- [Project commands](/customization/commands)
- [Project sub-agents](/customization/sub-agents)
- [MCP servers](/customization/mcp)
