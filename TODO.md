- [x] Include `/status` session usage dashboard (PR #392, merged 4998e974 on master after v0.51.0) in next release (v0.52.0)
- [x] Web terminal tab (PTY over WebSocket), Run-in-terminal for bash snippets, background-tasks icon → ActivityIcon
- [x] Web terminal: Windows now uses ConPTY via `pywinpty` (typing/echo/interactive prompts work)
- [x] Windows terminal review fixes: low-level pywinpty `PTY` backend (no loopback marker), errors reported to client, close kills process tree, ConPTY queries stripped from scrollback, bootstrap/`-i` for POSIX shells, no pipe fallback
- [x] Web terminal on Windows: default shell is `COMSPEC` (cmd.exe), consider preferring PowerShell; confirm in a real browser on a Windows host
- [x] `terminal-windows` job (windows-latest) added to `.github/workflows/tests.yml` for `tests/test_web_terminal.py`; not yet pushed, so unproven on a GitHub runner
- [x] Local session titles: background download of oot-oneliner GGUF + pinned official llama.cpp build at web start, generated title replaces first-message title (`session_titles.py`)
- [x] Local session titles: verify on macOS and Windows hosts (only Linux x64 exercised end to end)
- [x] Local session titles: no UI/status for download progress or opt-out besides `PBI_AGENT_LOCAL_TITLES=0`; CLI `run`, Telegram and runtime-created (`/new`) sessions still use truncated titles

- [x] Keep chat composer bottom-anchored when right-side panels open; regression tests for repeated files/tasks/terminal toggles and Chromium geometry checks at three viewport sizes.
- [x] Frontend validation for chat input anchoring: 751 web tests, lint, typecheck, build; browser confirms unchanged composer position across three viewport sizes.

- [x] Fix stale release-workflow notes ordering test; cover draft notes refresh and missing-file gate (23 workflow tests, Ruff lint/format, basedpyright passed).
- [x] Run full Python suite for release-workflow regression fix (passed).

- [x] Release v0.56.0 (#413, PR #412 Windows ConPTY terminal): validated, merged, PyPI + GitHub Release published

- [x] Badge text vertical centering across the web UI (cap-height trimmed label span; unlayered meta CSS override removed); 751 web tests, lint, typecheck, build, headless Chromium geometry + pixel checks.
- [x] Badge centering: expanded tool-result cards (`ToolResult`/`GitDiffResult` badges) not exercised in the browser run; Firefox without `text-box` support falls back to plain flex centering.

- [x] Sidebar session title tooltip when truncated; session title breadcrumb in topbar when sidebar is collapsed; fade-in when a generated title replaces the placeholder; no topbar overlap with right panels open (754 web tests, lint, typecheck, build, headless Chromium at 1440/1205/1000/800).
- [x] Topbar session title is hidden when the topbar is narrower than 36rem (phones, narrow split with a right panel); title animation still plays on a rename made elsewhere (other tab/CLI), since the frontend cannot tell who changed the title.
- [x] Code-review fixes for session-title UI (8 of 10 findings; 761 web tests, lint, typecheck, build, headless Chromium).
- [x] Keyboard focus on a clipped sidebar title that also scrolls the list into view showed no tooltip in one headless run (row 14); cause not confirmed.

- [x] #169 kits: `pbi-agent kits add <source> [--list] [--force]` one-shot copy of skills/commands/agents/MCP servers/instructions; docs + 8 tests.
- [x] #169 kits: default catalog `pbi-agent/kits` (public repo created, kits `coding`, `powerbi`, `research`, `customize`), `--kit NAME`, catalog listing; live-tested against GitHub.
- [x] #169 kits follow-ups (not built): no web UI/`/kits`; hooks and Python extensions not packaged; no kit ships MCP servers yet; kit files in `pbi-agent/kits` are copies of the skills/commands/agents catalogs and need manual re-sync.

- [x] #149 nested trace timeline in Run Detail modal (span tree, waterfall bars, sub-agent runs nested via new `child_runs` API field); 781 web tests, full pytest, static checks, build, headless Chromium dark/light/narrow.
- [x] #149 follow-ups (not built): parallel tool calls overlap in the waterfall (no lanes); running spans have no live indicator beyond the 2 s refetch; child AGENT rows have no detail panel (e.g. a failed sub-agent's error); bar column hidden below ~32rem container width.

- [x] #149 nested trace timeline in Run Detail modal: span tree with waterfall bars, sub-agent runs nested by tool call id, payloads loaded per event, in-flight spans, review findings addressed (787 web tests, full pytest, Ruff/format/basedpyright, lint/typecheck/build, headless Chromium dark/light/620px).
- [x] #149 not verified live: a new run whose sub-agent carries `parent_tool_call_id` (covered by unit/API tests only; existing DB runs predate it and show sub-agents under the parent run).
- [x] #149 follow-ups (not built): parallel tool calls overlap in the waterfall (no lanes); in-flight non-sub-agent tool calls are invisible until they return (no start event recorded); sub-agent AGENT rows have no detail panel; truncated-label tooltip may not show on rows without details (disabled button).

- [x] Release v0.57.0 (#419, PRs #414–#418): validated, merged, PyPI + GitHub Release published

- [x] Composer: tagging a skill `SKILL.md` via `@` inserts the highlighted `$skill-name` tag (788 web tests, lint, typecheck, build)
- [x] Composer skill tagging verified in headless Chromium against the live server (port 7431)
- [x] Composer skill tagging: typed or pasted `@…/SKILL.md` paths stay as file mentions (by design for now)
- [x] Composer tag highlights styled as padded pills matching timeline tags (ring + offset outline; Composer tests, lint, typecheck, build, headless Chromium)
- [x] Composer pills: two tags separated by a single space touch (3px painted outside each box, no layout space available)
- [x] Skill tags violet (`usage-violet`) in composer and timeline (session tests, lint, typecheck, build, headless Chromium)

- [x] Composer keeps unsent text when toggling top-right panels or switching sessions (stable panel tree + in-memory draft; web tests, lint, typecheck, build, headless Chromium)
- [x] Composer draft: pending images and reply snippets are still dropped on route changes (kept on panel toggles); draft is one shared text, not per session

- [x] On-device speech-to-text: Parakeet v3 int8 ONNX on pinned sherpa-onnx CLI, built-in "On this device" option in Speech settings with download progress/retry, long recordings split at quiet points (15 Python tests, 3 web tests, full suites, lint/typecheck/build, docs build, headless Chromium against an isolated server with real download + transcription)
- [x] On-device STT: only Linux x64 executed; macOS (unsigned binary/Gatekeeper), Windows x64/arm64 and Linux arm64 builds are pinned but unrun
- [x] On-device STT: quality checked only on clean samples (JFK clip, en/de/fr/es test wavs); not on real dictation with technical vocabulary. pbi-agent's own resampler changes punctuation slightly vs sherpa-onnx resampling the original file (words identical)
- [x] On-device STT follow-ups (not built): model reload costs ~1.8 s per piece (a long-lived `sherpa-onnx-offline-websocket-server` would remove it for ~1.1 GB held RAM); no way to delete the downloaded model from the UI; no forced language

- [x] Dictation recording indicator replaced with `DictationTimeline` (dot + timer + scrolling loudness history); 796 web tests, lint, typecheck, build, headless Chromium dark/light with a fake microphone
- [ ] Dictation timeline: checked only with Chromium's synthetic beep input, not a real voice; bar sensitivity (`NOISE_FLOOR`, 0.7 curve) may need tuning on a real microphone

- [x] Release v0.58.0 (#423, PRs #420–#422): validated, merged, PyPI + GitHub Release published

- [x] Session topbar TODO shortcut (ListTodo toggle + Alt+Shift+T) opening a right side-panel tab (like files/tasks/terminal) that renders workspace `TODO.md` files (tabs when several, status icons for `[ ]`/`[x]`/`[>]`/`[!]`/`[-]`, counts, 3 s live refresh); 804 web tests, lint, typecheck, build, headless Chromium dark/light
- [ ] TODO shortcut: button only appears when the file tree index lists a `TODO.md` (gitignored or truncated-index files are missed); Alt+Shift+T still opens the panel empty state
- [x] TODO panel: status count badges are filter toggles (one active at a time, click again to clear; parents of matching sub-items stay dimmed); 805 web tests, lint, typecheck, build, headless Chromium
- [x] Release v0.59.0 (#425, PR #424 TODO panel + status filters): validated, merged, PyPI + GitHub Release published

- [x] Windows `WinError 5` on local STT install: `local_assets._replace` falls back to copying when antivirus blocks the final rename; tests in `tests/test_local_assets.py`
- [ ] Confirm the copy fallback on a real Windows host (copy fallback + best-effort cleanup of the locked `.tmp`)
- [x] Release v0.60.0 (#428, PRs #426 system_info + #427 Windows copy fallback): validated, merged, PyPI + GitHub Release published
- [x] `pbi-agent run`: default to final response only; `--show-steps` shows all intermediate steps (run + sandbox run, docs/cli.md, tests)
