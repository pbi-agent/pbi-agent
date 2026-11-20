# pbi-agent web

Serve the browser UI for the current workspace and open it in your browser. This is the default command when none is given.

## Purpose
Use `web` for interactive work: chat sessions, Kanban board, settings, providers and profiles, terminals. It serves a local FastAPI app for the current working directory (the workspace) and keeps running until Ctrl+C. Use `pbi-agent run` for one scripted turn, and `pbi-agent sandbox web` to serve the same UI from a Docker container. `pbi-agent` with no command, or with only non-runtime global options, runs `web`.

## Usage
```text
pbi-agent [GLOBAL OPTIONS] web [--host HOST] [--port PORT] [--dev] [--title TITLE] [--url URL]
```

## Options and arguments
- `--host HOST`: interface to bind. Default `127.0.0.1`. With `0.0.0.0` or `::` the browser is opened on the loopback address.
- `--port PORT`: port to bind, 1-65535 (out of range exits 2). Default `7424`. When the port is left at the default and 7424 is busy, a free port is picked and reported on stderr; an explicit `--port` is used as given, even if busy.
- `--dev`: development mode: allows CORS from the Vite dev/preview servers (`localhost`/`127.0.0.1` ports 5173 and 4173) and uses info-level server logs.
- `--title TITLE`: override the browser page title.
- `--url URL`: public URL for reverse-proxy setups. It is shown as the serving address and opened in the browser instead of `http://HOST:PORT`; `http://` is prepended when it has no scheme.

## Examples
```bash
# Start the UI for the current directory (same as plain `pbi-agent`)
pbi-agent web

# Pick a fixed port
pbi-agent web --port 9001

# Listen on all interfaces behind a reverse proxy
pbi-agent web --host 0.0.0.0 --port 7424 --url https://agent.example.com

# Verbose logs (global options go before the command)
pbi-agent --verbose web
```

## Workflows
1. First start: `pbi-agent web`; if no web profile is active the server still starts and the UI sends you to Settings to create a provider and model profile.
2. Configure from the terminal instead: `pbi-agent config providers create ...`, `pbi-agent config profiles create ...`, `pbi-agent config profiles select <profile-id>`, then `pbi-agent web`.
3. Hand off to scripts: work interactively in `web`, then continue a session with `pbi-agent run --session-id <id> -p "..."` (IDs from `pbi-agent sessions`).

## Related commands
- `pbi-agent run`: one non-interactive turn; the place for runtime provider/model flags.
- `pbi-agent sandbox web`: the same UI with the agent running inside Docker.
- `pbi-agent config profiles`: manage and select the profile the web UI uses by default.
- `pbi-agent sessions`: list the sessions the UI created.

## Pitfalls
- Runtime provider/model global flags (`--provider`, `--model`, `--profile-id`, `--api-key`, `--max-tokens`, `--reasoning-effort`, ...) are rejected with `web`, including the implicit default `web`: exit 2. Configure the UI in Settings or with `pbi-agent config profiles select`.
- `--verbose` and `--dangerously-bypass-hook-trust` are allowed, but must come before `web`.
- Only one web server may manage a workspace at a time; a second one exits 1 with `another web app instance is already managing this workspace`.
- The browser opens automatically once the server accepts connections (on WSL it tries the Windows browser). Stop the server with Ctrl+C.
- `--d` is ambiguous (`--dev` and `--doc`); spell options out.
- Binding `0.0.0.0` exposes the agent, with shell and file tools, to your network.
