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

- Prior implementation/validation notes: `.agents/memory/2026-11-13.md` (#149 trace timeline, composer skill tags/draft, headless-check recipe, Settings add-dialog scrolling, OpenAI/Claude pricing refresh + Claude ID dedup, trace token column, releases v0.57–v0.62), `.agents/memory/2026-11-12.md` (web terminal/ConPTY, local session titles, badge centering, session-title UI, #169 kits, releases v0.53–v0.56), `.agents/memory/2026-11-10.md` (includes #292 interrupt cleanup, #199 status dashboard, #344 questionnaire). [verified 2026-11-12]

## Daily Log

### 2026-11-18
- Bumped `CHATGPT_CODEX_VERSION` 0.159.2 → 0.170.0 (`chatgpt_codex_backend.py`; drives User-Agent + model-discovery `client_version`). Ruff + codex/chatgpt/model-discovery/openai tests green. [verified 2026-11-18]
- Added `gpt-6.2-astra` (8/40, cached 0.4, write 10) and `gpt-6.2-sol` (2/10, cached 0.1, write 2.5) using short-context rates; 30m write fills both write fields (12h/long-context tiers unrepresentable). Pricing regressions added; usage tests, Ruff/format passed. [verified 2026-11-18]
- Chat Completions `finish_reason: content_filter` now raises a non-retryable `SemanticResponseError` via `raise_if_content_filtered` (`protocols/chat_completions.py`), wired into generic, GCP chat-completions, and Copilot chat loop; surfaces as web `role: error` message with refusal/partial output/filter categories. Reported `usage` rides on `SemanticResponseError.usage` and is added to session/turn totals via `record_failed_response_usage` (`providers/runtime.py`) + failure trace. Full pytest + basedpyright green. [verified 2026-11-18]
- Windows `pbi-agent upgrade` "hang": the deferred PowerShell installer shared the user's console, so uv output printed after the shell had redrawn its prompt (it was never blocked). It now runs via `Popen(..., creationflags=CREATE_NEW_CONSOLE)` (`cli/upgrade.py`), and the script (`self_update.windows_deferred_command`) closes after 5s on success or waits for Enter on failure. Upgrade tests, Ruff, basedpyright and docs build pass; not run on real Windows. [unverified on Windows]
- Hardened Windows deferred upgrade script (`self_update.windows_deferred_command`, now takes `installer`/`interactive`/`python`/`current_version`): `$code` defaults to 1 + try/catch (a missing installer left `$LASTEXITCODE` `$null` → `exit $null` = 0, verified), post-install version check via the env's `python -c` (exit 3 = still old → failure), no double quotes, pauses only when `sys.stdin.isatty()` (5s/any key on success, Read-Host on failure). Real-PowerShell integration tests in `tests/test_self_update.py` (win32-only); CREATE_NEW_CONSOLE launch verified on Win11 26300. Trap: ~32 unrelated tests fail on Windows (Rich column truncation etc.). [verified 2026-11-18]
- Released v0.65.0 (#444: #442, #443 Windows upgrade fixes); Release run 44372609605 green incl. PyPI publish; release body verified. [verified 2026-11-18]
