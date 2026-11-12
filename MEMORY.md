# MEMORY.md

Index of durable project memory, preloaded into every main-agent session (first 200 lines / 25 KB only). Keep it short: goal, top rules, open follow-ups, links. Details live in `.agents/memory/*.md`. Conventions already in `AGENTS.md` or config are not repeated here.

Entry shape: rule/fact — why/evidence — `[verified YYYY-MM-DD]` or `[unverified]`. Untagged entries predate this convention (migrated 2026-11-07).

## Current Focus
- Memory redesign (2026-11-07): index + topic pages, capped injection; memory rules and session-DB query guidance live only in `AGENTS.md`, never in the system prompt code (user decision). [verified 2026-11-07]

## Top Rules
- No migrations or backward-compat shims unless asked.
- Report skipped, hung, or broken checks instead of claiming green.
- `web:build` must run `bun --bun vite build`; Node-run Vite changes chunk hashes → CI static-asset drift. See `tooling.md`.
- Never rerun an old-SHA release; PyPI CDN lags, verify instead of republishing. See `tooling.md`.
- ChatGPT/Copilot: never replay `reasoning_text`+`reasoning_opaque` on tool-call messages (422). See `providers.md`.

## Open Follow-Ups
- Follow-ups: post-delivery interrupt removes the accepted live user item; accepted steers should stay. (`web.md`)
- ChatGPT continuation: live-unverified recovered-ID reuse, delayed/encrypted-reasoning recovery, proactive replay. (`providers.md`)
- Packaging: transitive security minima are lock-only, not in published runtime metadata. (`tooling.md`)
- Unverified on real hosts: Windows self-update path; Linux GUI browser launch. (`tooling.md`)

## Topic Pages
- `.agents/memory/tooling.md`: Ruff exceptions, tool pins, test hygiene, releases, upgrade, security.
- `.agents/memory/providers.md`: provider internals, Copilot, xAI, models/pricing, reasoning, OpenAI/ChatGPT, Google.
- `.agents/memory/tools.md`: read_image, shell, background shell, `allowed_tools`, patching, MCP.
- `.agents/memory/runtime.md`: prompt assembly, catalogs, sub-agents, commands, replay, hooks, sandbox/init, branding.
- `.agents/memory/web.md`: API contracts, web sessions, channels, events, timeline, UI quirks, composer, follow-ups.

- Prior implementation/validation notes: `.agents/memory/2026-11-10.md` (includes #292 interrupt cleanup, #199 status dashboard, #344 questionnaire). [verified 2026-11-12]

## Daily Log

### 2026-11-12
- #393: raw-output notices reference `raw_output_path` instead of repeating the file path; background completion text renders a separate path field. 88 targeted tests + Ruff/format/basedpyright passed.
- CLI welcome: moved model/reasoning from clipped Rich panel subtitle into wrapping body; regression coverage at 32/80/160 columns. 26 targeted tests + Ruff/format/basedpyright passed.
- CLI `run` now goes through `web/session/headless.py::HeadlessSessionChannel` (same LiveSessionState/WebDisplay/`web_session` run + `web_event` persistence as web), console rendered via `TeeDisplay`; CLI sessions open in web UI with identical timeline. `run` default profile = `config.web.active_profile_id` when no flags (already, verified). Pre-existing failure: `test_execute_tool_calls_serializes_compressed_shell_output` (fails on clean tree too).
- Badge `meta` size: fixed h-5 + py-0 + leading-none to center text (was asymmetric py-[2px]/pb-[3px]). Web tests/lint/typecheck/build passed.
- Web terminal: `web/terminal.py` (PTY shell = `PBI_AGENT_SHELL_EXECUTABLE`/`$SHELL`, bootstrap sourced) + WS `/api/terminals/ws` (same-origin check), `TerminalPanel` (xterm) topbar toggle `SquareTerminalIcon`; background tasks now `ActivityIcon`; bash/sh md snippets get Run button. Tests/lint/types/build green; live-verified with Playwright headless (needed libnspr4/libnss3/libasound via `apt-get download` + LD_LIBRARY_PATH).
- Snippet Run button: ghost→outline variant (ghost hover = bg-muted, invisible on muted snippet header; lint forbids Button color overrides). Web tests/lint/types/build green.
- Bash snippet header: Run pinned top-right, hover-revealed copy shortcut inline to its left (non-shell snippets keep floating copy). Web tests/lint/types/build green.
- /review fixes: terminal WS now requires trusted Host (IP literal/localhost or `--url` host) to block DNS rebinding; manager prunes exited detached terminals. Terminal+serve tests, Ruff/format/basedpyright green.
- Background tasks topbar toggle icon: `ActivityIcon` → `LayersIcon` (SessionPage). Web tests/lint/typecheck/build green.
- Release workflow: draft step now strips VitePress frontmatter from `docs/changelog/v<version>.md` into `$RUNNER_TEMP` notes (+ `Full changelog:` line), fails pre-PyPI unless body starts `# v<version>`, and refreshes notes on reused drafts. awk tested on v0.52.0/v0.51.0/v0.9.0; YAML parses. Release skill/command updated.
