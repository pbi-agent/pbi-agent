---
title: 'Workspace Reload'
description: 'Refresh workspace prompt files and project catalogs in a live session.'
---

# Workspace Reload

New one-shot runs and newly created sessions read the current workspace
initialization files when their provider starts. A live session keeps its
provider open between turns, so edits to workspace files are not applied to that
active provider until you reload it.

Use the local session command:

```text
/reload
```

`/reload` does not call the model and is not stored as a user message. It
refreshes the current live provider before the next model request by re-reading:

- `INSTRUCTIONS.md`
- `AGENTS.md`
- project skill catalogs
- project sub-agent catalogs
- non-MCP tool definitions

In the web UI, `/reload` also refreshes the `@file` mention cache so newly
created, renamed, or removed workspace files show up in autocomplete. The web
app also refreshes that file-mention cache when a live session ends, which keeps
the next session's file suggestions current without silently changing an active
provider mid-task.

See [Session Commands](/session-commands) for the full `@file`, `!shell`, and
slash-command reference.

`/reload` does not reload MCP server configuration or MCP tool catalogs for the
active provider. Restart the session after changing `.agents/mcp.json` or an MCP
server's exposed tools.
