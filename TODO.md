- [x] Include `/status` session usage dashboard (PR #392, merged 4998e974 on master after v0.51.0) in next release (v0.52.0)
- [x] Web terminal tab (PTY over WebSocket), Run-in-terminal for bash snippets, background-tasks icon → ActivityIcon
- [x] Web terminal: Windows now uses ConPTY via `pywinpty` (typing/echo/interactive prompts work)
- [x] Windows terminal review fixes: low-level pywinpty `PTY` backend (no loopback marker), errors reported to client, close kills process tree, ConPTY queries stripped from scrollback, bootstrap/`-i` for POSIX shells, no pipe fallback
- [ ] Web terminal on Windows: default shell is `COMSPEC` (cmd.exe), consider preferring PowerShell; confirm in a real browser on a Windows host
- [>] `terminal-windows` job (windows-latest) added to `.github/workflows/tests.yml` for `tests/test_web_terminal.py`; not yet pushed, so unproven on a GitHub runner
- [x] Local session titles: background download of oot-oneliner GGUF + pinned official llama.cpp build at web start, generated title replaces first-message title (`session_titles.py`)
- [ ] Local session titles: verify on macOS and Windows hosts (only Linux x64 exercised end to end)
- [ ] Local session titles: no UI/status for download progress or opt-out besides `PBI_AGENT_LOCAL_TITLES=0`; CLI `run`, Telegram and runtime-created (`/new`) sessions still use truncated titles

- [x] Keep chat composer bottom-anchored when right-side panels open; regression tests for repeated files/tasks/terminal toggles and Chromium geometry checks at three viewport sizes.
- [x] Frontend validation for chat input anchoring: 751 web tests, lint, typecheck, build; browser confirms unchanged composer position across three viewport sizes.

- [x] Fix stale release-workflow notes ordering test; cover draft notes refresh and missing-file gate (23 workflow tests, Ruff lint/format, basedpyright passed).
- [x] Run full Python suite for release-workflow regression fix (passed).

- [x] Release v0.56.0 (#413, PR #412 Windows ConPTY terminal): validated, merged, PyPI + GitHub Release published

- [x] Badge text vertical centering across the web UI (cap-height trimmed label span; unlayered meta CSS override removed); 751 web tests, lint, typecheck, build, headless Chromium geometry + pixel checks.
- [ ] Badge centering: expanded tool-result cards (`ToolResult`/`GitDiffResult` badges) not exercised in the browser run; Firefox without `text-box` support falls back to plain flex centering.

- [x] Sidebar session title tooltip when truncated; session title breadcrumb in topbar when sidebar is collapsed; fade-in when a generated title replaces the placeholder; no topbar overlap with right panels open (754 web tests, lint, typecheck, build, headless Chromium at 1440/1205/1000/800).
- [ ] Topbar session title is hidden when the topbar is narrower than 36rem (phones, narrow split with a right panel); title animation still plays on a rename made elsewhere (other tab/CLI), since the frontend cannot tell who changed the title.
- [x] Code-review fixes for session-title UI (8 of 10 findings; 761 web tests, lint, typecheck, build, headless Chromium).
- [ ] Keyboard focus on a clipped sidebar title that also scrolls the list into view showed no tooltip in one headless run (row 14); cause not confirmed.

- [x] #169 kits: `pbi-agent kits add <source> [--list] [--force]` one-shot copy of skills/commands/agents/MCP servers/instructions; docs + 8 tests.
- [x] #169 kits: default catalog `pbi-agent/kits` (public repo created, kits `coding`, `powerbi`, `research`, `customize`), `--kit NAME`, catalog listing; live-tested against GitHub.
- [ ] #169 kits follow-ups (not built): no web UI/`/kits`; hooks and Python extensions not packaged; no kit ships MCP servers yet; kit files in `pbi-agent/kits` are copies of the skills/commands/agents catalogs and need manual re-sync.

- [x] #149 nested trace timeline in Run Detail modal (span tree, waterfall bars, sub-agent runs nested via new `child_runs` API field); 781 web tests, full pytest, static checks, build, headless Chromium dark/light/narrow.
- [ ] #149 follow-ups (not built): parallel tool calls overlap in the waterfall (no lanes); running spans have no live indicator beyond the 2 s refetch; child AGENT rows have no detail panel (e.g. a failed sub-agent's error); bar column hidden below ~32rem container width.

- [x] #149 nested trace timeline in Run Detail modal: span tree with waterfall bars, sub-agent runs nested by tool call id, payloads loaded per event, in-flight spans, review findings addressed (787 web tests, full pytest, Ruff/format/basedpyright, lint/typecheck/build, headless Chromium dark/light/620px).
- [ ] #149 not verified live: a new run whose sub-agent carries `parent_tool_call_id` (covered by unit/API tests only; existing DB runs predate it and show sub-agents under the parent run).
- [ ] #149 follow-ups (not built): parallel tool calls overlap in the waterfall (no lanes); in-flight non-sub-agent tool calls are invisible until they return (no start event recorded); sub-agent AGENT rows have no detail panel; truncated-label tooltip may not show on rows without details (disabled button).
