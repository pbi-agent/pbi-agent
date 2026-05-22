---
title: 'MCP Servers'
description: 'Expose project-local MCP server tools through .agents/mcp.json.'
---

# MCP Servers

`pbi-agent` can discover project-local MCP server definitions and expose their
tools to the model as ordinary function tools. The runtime reads a single JSON
file from the workspace root:

- `.agents/mcp.json`

The file must contain a top-level `servers` object. Each entry can be either:

- `type: "stdio"` with `command`, optional `args`, optional `env`, and optional
  `cwd`
- `type: "http"` with `url` and optional `headers`

Example:

```json
{
  "servers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp"
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@microsoft/mcp-server-playwright"]
    }
  }
}
```

Discovered MCP tools are added to the model-facing tool list at startup. In the
UI, you can inspect the discovered server list with `/mcp`, or from the CLI with
`pbi-agent --mcp`.

::: tip
Model-facing MCP tool names are namespaced per server, so a tool like `say_hi`
from the `echo` server is exposed as `echo__say_hi`.
:::

`/reload` does not reload MCP server configuration or already-started MCP tool
catalogs. Restart the session after changing `.agents/mcp.json` or an MCP
server's exposed tools.
