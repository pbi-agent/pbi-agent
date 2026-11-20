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

- Prior implementation/validation notes: `.agents/memory/2026-11-18.md` (Codex client version, GPT-6.2 pricing, Chat Completions content filtering, Windows upgrade assistant, v0.65.0 release), `.agents/memory/2026-11-13.md` (#149 trace timeline, composer skill tags/draft, headless-check recipe, Settings add-dialog scrolling, OpenAI/Claude pricing refresh + Claude ID dedup, trace token column, releases v0.57–v0.62), `.agents/memory/2026-11-12.md` (web terminal/ConPTY, local session titles, badge centering, session-title UI, #169 kits, releases v0.53–v0.56), `.agents/memory/2026-11-10.md` (includes #292 interrupt cleanup, #199 status dashboard, #344 questionnaire). [verified 2026-11-12]

## Daily Log

### 2026-11-20
- Assistant timeline file links (including stored relative Markdown and same-origin `/sessions/…` URLs) now reveal the workspace file in Explorer without navigation. Session log confirmed `docs/04_commercial_assessment.md` and an encoded-space report link. Resolution is frontend-only; preview confinement remains server-side. Web suite, focused regressions, typecheck, lint, and Bun bundle passed. [verified 2026-11-20]
- Markdown HTTP(S) and protocol-relative links now default to a new tab; assistant workspace links still use the Explorer click handler. Rebuilt the packaged frontend; 838 web tests, typecheck, and lint passed. [verified 2026-11-20]
- Review fixes for workspace file links (`workspaceFileLinks.ts`): `path:line[:col]` suffixes stripped; absolute/`file://`/Windows-drive paths under `workspaceRoot` mapped to workspace paths; raw relative hrefs always open in Explorer (they can only resolve under `/sessions/`); sub-agent-expanded `/sessions/<id>/sub-agents/<rel>` stripped. Link handler reads the tree from the query cache on click so context stays stable. Kept deliberately: raw (not diff) preview on reveal, filter reset on reveal. 853 web tests, lint, typecheck, web:build passed. [verified 2026-11-20]
- Workspace file links now jump to lines: `workspaceFileTargetForLink` returns `{path, lines}` from `:42`, `:42:7`, `:42-50`, `#L42`, `#L42-L50`; Explorer keeps the range until a tree pick; `CodeBlock` `highlightLines` marks `span.line` rows (`data-line-highlight`, full-width `inline-block min-w-full align-top`) and centers the first. Markdown files with a line target show source. `MarkdownContent` `urlTransform` keeps `name.ext:N` hrefs (react-markdown otherwise blanks them as a scheme). 875 web tests, lint, typecheck, build; live-checked display.py:120-123 and README.md#L12. [verified 2026-11-20]
- Web chat sessions get a chat-interface section in the main-agent system prompt (`_CHAT_INTERFACE_PROMPT` in `system_prompt.py`, after project rules): bash/sh fences get a Run button, `path:42`/`:42-50` file links open in the in-app preview, https links open a new tab. Web-only via `get_system_prompt(chat_interface=True)`, passed only from `run_session_loop` (web chat worker) prompt builders; CLI `run`, board tasks (`run_single_turn`) and sub-agents omit it. Full pytest, ruff, basedpyright passed. [verified 2026-11-20]
