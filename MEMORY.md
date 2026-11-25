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
- Background tasks: Windows `tty` (ConPTY) unsupported; 46 catalog entries lack `context_window` (user adds them); single-turn end-of-turn wait has no time cap and wake turns are not persisted (open design calls). (`tools.md`)

## Topic Pages
- `.agents/memory/tooling.md`: Ruff exceptions, tool pins, test hygiene, releases, upgrade, security.
- `.agents/memory/providers.md`: provider internals, Copilot, xAI, models/pricing, reasoning, OpenAI/ChatGPT, Google.
- `.agents/memory/tools.md`: read_image, shell, background shell, `allowed_tools`, patching, MCP.
- `.agents/memory/runtime.md`: prompt assembly, catalogs, sub-agents, commands, replay, hooks, sandbox/init, branding.
- `.agents/memory/web.md`: API contracts, web sessions, channels, events, timeline, UI quirks, composer, follow-ups.

- Prior implementation/validation notes: `.agents/memory/2026-11-20.md` (workspace file links + line targets, web chat-interface prompt, prompt compression, multi-install dialogs, `/factory` pipeline + learn passes, #449 `--doc` guides, #450 table scroll, #455 tool-less requests, v0.66.0 release), `.agents/memory/2026-11-18.md` (Codex client version, GPT-6.2 pricing, Chat Completions content filtering, Windows upgrade assistant, v0.65.0 release), `.agents/memory/2026-11-13.md` (#149 trace timeline, composer skill tags/draft, headless-check recipe, Settings add-dialog scrolling, OpenAI/Claude pricing refresh + Claude ID dedup, trace token column, releases v0.57–v0.62), `.agents/memory/2026-11-12.md` (web terminal/ConPTY, local session titles, badge centering, session-title UI, #169 kits, releases v0.53–v0.56), `.agents/memory/2026-11-10.md` (includes #292 interrupt cleanup, #199 status dashboard, #344 questionnaire). [verified 2026-11-12]

## Daily Log

### 2026-11-24
- Codex-inspired harness pass (plan in session scratchpad, not repo): 90% auto-compaction (`effective_compact_threshold`), plain-text tool output for all providers (`tools/model_output.py`, `ToolResult.output`/`payload`), shell `yield_time_ms` replaces `timeout_ms` with auto-yield to background, fg stdin closed, `tty` + `background_task input` + delta reads, background tasks in `run`/board/sub-agents (`agent/session/background.py`). Full pytest (2587), ruff, format, basedpyright, 894 web tests, lint, typecheck, docs build, Bun 1.4.4 bundle (via `bunx bun@1.4.4 run web:build`, verified byte-identical on clean HEAD) passed. Not live-tested with a real provider; Windows `tty` unsupported. Details: `tools.md`, `runtime.md`. [verified 2026-11-24]

### 2026-11-25
- Live check of the Codex-inspired harness pass (scratch DBs, scratch workspace): `run` auto-yield + delta read (ChatGPT gpt-6.2-astra), `tty` Python REPL via `background_task input` with Ctrl-C/Ctrl-D (gpt-6.2-astra), `run` end-of-turn background wake (Copilot claude-haiku-5.5, chat-completions got plain text), web chat auto-yield → follow-up wake (port 7437). All passed. Fixes from it: web user `!` commands set `ToolContext.background_handoff=False` (else a >30s user command would be handed to the model's background tasks and wake it); display/API/UI `timeout_ms` metadata renamed `yield_time_ms` (shell card shows `yield Nms`, api-types regenerated); simple `tty` commands are `exec`ed. Trap: Python REPL exits -2 on Ctrl-D after a KeyboardInterrupt (Python behavior, not the harness). Full checks + Bun 1.4.4 bundle passed. [verified 2026-11-25]
- Code review of the harness branch, 8 of 10 findings fixed: timeline `parseBackgroundResult` now parses the `task_id`-only tag + header line (`<status>[ · dur][ — intent]`); `render_generic` prints compact JSON when every value is false/empty; `_tty_command` wraps in `case "$(command -v X)" in /*) exec …;; *) …;; esac`; foreground `tty` output cleaned; failed hand-off names the reason; `adopt(stdout_cursor=, stderr_cursor=)`; wake wait raises on interrupt; `wait_for_output(seen=)`. Left as designed: uncapped single-turn wait, unpersisted wake turns. 2602 pytest, ruff, format, basedpyright, 897 web tests, lint, typecheck, Bun 1.4.4 bundle passed. [verified 2026-11-25]
- Live check of the review fixes (CLI `run` with Copilot claude-haiku-5.5, web chat on port 7438 with gpt-6.2-sol, scratch DBs): `tty` `cd .` exit 0, `ls -1` clean, `input` with `wait_ms` 20000 returned in 359 ms, hand-off wake showed only new output, timeline card `Background task <intent> · exit 0 · 4.0s`. Two fixes from it: timed-out payload carries `handoff_error`, rendered as `killed, not moved to background: …` (the renderer hides `error` on timeouts); `background_task kill` on a still-running task renders `kill requested <id>`. Trap: `timeout -s INT` around `uv run` also interrupts the calling shell; read results from the scratch DB. Not live-checked: `display.interrupt_requested` during the end-of-turn wait. 2604 pytest, ruff, format, basedpyright passed. [verified 2026-11-25]
- Background result header no longer repeats the task id (the tag carries it): first line is `<status>[ · dur][ — intent]`; `parseBackgroundResult` no longer strips an id prefix. `background_task` tool output still starts with the id. [verified 2026-11-25]
- OpenAI Responses function tools now send `strict: false` (`OpenAIProvider.refresh_tools`; covers API-key OpenAI, ChatGPT-Codex backend, Copilot Responses subclass). Why: with `strict` omitted GPT emitted every optional param with invented values (262/262 recorded `chatgpt` shell calls, e.g. `compression: false`); Codex sends `strict: false` on all tools. xAI/Google emitters untouched. 2604 pytest, ruff, format, basedpyright passed. Live check (`run`, scratch DB, gpt-6.2-astra): shell call sent only `command` + `intent`. [verified 2026-11-25]
- ChatGPT-Codex backend now sends the system prompt as the first `developer` input item instead of top-level `instructions` (`ResponsesRequestOptions.instructions_as_developer_input`; only on full payloads, chained `previous_response_id` requests carry it), and sends `session-id` + `thread-id` headers instead of `session_id`. Why: `usage.attribution` showed `instructions` never served from cache (0/5853 on 17 calls); upstream Codex `cec14d2` has no `instructions` field. Live `run` (gpt-6.2-sol): call 2 cached 6144/6417, was 0. One full-miss call per session still occurs (seen before and after), cause unknown. Validation: ruff, basedpyright, pytest 2605 passed. [verified 2026-11-25]
