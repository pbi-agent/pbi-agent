# pbi-agent sandbox web

Serve the browser UI from inside the Docker sandbox, publish it on a host port, and open the host browser.

## Purpose
Use `sandbox web` for interactive sessions whose tools must execute in the container instead of on the host. It is also what plain `pbi-agent sandbox` runs. Inside the container the server runs `pbi-agent web --host 0.0.0.0 --port PORT` with browser launch disabled; the host CLI publishes `HOST:PORT` to the same container port and opens the browser itself after the server responds (plus a short grace delay). Use `pbi-agent web` for the same UI without Docker. Sandbox options (`--image`, `--env-file`, `--rebuild`, `--local-source`, `--read-only-repo`, `-d`) are described in `pbi-agent sandbox --doc`.

## Usage
```text
pbi-agent [GLOBAL OPTIONS] sandbox [SANDBOX OPTIONS] web [--host HOST] [--port PORT] [--dev] [--title TITLE] [--url URL]
```

## Options and arguments
- `--host HOST`: host interface the container port is published on. Default `127.0.0.1`. Inside the container the server always binds `0.0.0.0`.
- `--port PORT`: host and container port, 1-65535 (out of range exits 2). Default `7424`. If left at the default and 7424 is busy, a free port is picked and reported on stderr. An explicit `--port` that is busy on the host exits 1 with `host port N is unavailable for sandbox web`.
- `--dev`: pass `--dev` to the inner `pbi-agent web` (development mode).
- `--title TITLE`: pass a browser title override to the inner server.
- `--url URL`: public URL for reverse-proxy setups; passed to the inner server and used as the host browser target (`http://` is prepended when it has no scheme).

## Examples
```bash
# Start the sandboxed UI in the foreground
pbi-agent sandbox web

# Another port, in the background
pbi-agent sandbox -d web --port 9001

# Read-only repository with credentials from an env file
pbi-agent sandbox --env-file .env.sandbox --read-only-repo web

# Verbose logs inside the container
pbi-agent --verbose sandbox web --dev
```

## Workflows
1. Foreground session: `pbi-agent sandbox web`, work in the browser, then Ctrl+C in the terminal to stop and remove the container.
2. Background session: `pbi-agent sandbox -d web`, note the printed container ID, later `docker stop <container-id>`.
3. Set the model first: the sandboxed UI uses the saved web profile from the shared `~/.pbi-agent`, so run `pbi-agent config profiles select <profile-id>` on the host (or pick it in Settings), then `pbi-agent sandbox web`.

## Related commands
- `pbi-agent sandbox`: parent command; image, env file, mounts and detach options.
- `pbi-agent web`: the same UI on the host.
- `pbi-agent sandbox run`: one prompt turn in the sandbox instead of a server.

## Pitfalls
- Sandbox options go before `web`: `pbi-agent sandbox -d web`, not `pbi-agent sandbox web -d` (exit 2).
- Unlike host `web`, global runtime flags (`--model`, `--profile-id`, ...) are not rejected; they are forwarded as `PBI_AGENT_*` env vars, but the web UI picks its model from saved profiles, not from them.
- The workspace is the current directory; start it from the repository root. Only one sandbox per folder name can run at a time (container name `pbi-agent-<folder name>`).
- `--host 0.0.0.0` publishes the UI, and the agent's tools, to your network.
- `--d` is ambiguous (`--dev` and `--doc`); spell options out.
