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
- Badge vertical centering (supersedes earlier `meta` padding/leading tweaks) [verified 2026-11-12]: root cause was an unlayered `[data-variant][data-size="meta"]` rule in `index.css` overriding the cva classes (asymmetric 2px/3px padding) plus font ascent/descent (Consolas on Windows: caps 1.5px high). Fix: rule deleted; `Badge` groups text children into `span[data-slot=badge-label]`, base class trims direct spans with `text-box: trim-both cap alphabetic`, `meta` = `h-6 py-0 leading-none`. Tests must reach the badge via `.closest('[data-slot="badge"]')`. A truncating label inside a badge needs `overflow-x-clip text-ellipsis`, not `truncate` (would clip ascenders). Verified in headless Chromium with `FONTCONFIG_FILE` including `/mnt/c/Windows/Fonts` (Consolas/Courier New): label centre within 0.01px of badge centre on sessions, board, dashboard, tasks/terminal panels, all settings tabs. 751 web tests/lint/types/build green.
- Web terminal: `web/terminal.py` (PTY shell = `PBI_AGENT_SHELL_EXECUTABLE`/`$SHELL`, bootstrap sourced) + WS `/api/terminals/ws` (same-origin check), `TerminalPanel` (xterm) topbar toggle `SquareTerminalIcon`; background tasks now `ActivityIcon`; bash/sh md snippets get Run button. Tests/lint/types/build green; live-verified with Playwright headless (needed libnspr4/libnss3/libasound via `apt-get download` + LD_LIBRARY_PATH).
- Snippet Run button: ghost→outline variant (ghost hover = bg-muted, invisible on muted snippet header; lint forbids Button color overrides). Web tests/lint/types/build green.
- Bash snippet header: Run pinned top-right, hover-revealed copy shortcut inline to its left (non-shell snippets keep floating copy). Web tests/lint/types/build green.
- /review fixes: terminal WS now requires trusted Host (IP literal/localhost or `--url` host) to block DNS rebinding; manager prunes exited detached terminals. Terminal+serve tests, Ruff/format/basedpyright green.
- Background tasks topbar toggle icon: `ActivityIcon` → `LayersIcon` (SessionPage). Web tests/lint/typecheck/build green.
- Release workflow: draft step now strips VitePress frontmatter from `docs/changelog/v<version>.md` into `$RUNNER_TEMP` notes (+ `Full changelog:` line), fails pre-PyPI unless body starts `# v<version>`, and refreshes notes on reused drafts. awk tested on v0.52.0/v0.51.0/v0.9.0; YAML parses. Release skill/command updated.
- Local session titles: `session_titles.py` downloads oot-oneliner Q4_K_M GGUF (HF, pinned commit+sha256) and official llama.cpp `b12320` CPU build (per-platform sha256) into `~/.pbi-agent/title-model` from a lifespan thread; `_ensure_saved_session_title` then swaps the 80-char placeholder for a `llama-completion` one-shot title unless renamed. Flags that matter: `-t/-tb` = half logical CPUs (all CPUs cost ~3 s), `-fa off` (flash attention changes outputs), prompt file needs doubled trailing newline. Tests disable via autouse `PBI_AGENT_LOCAL_TITLES=0`. 18 new tests + Ruff/format/basedpyright green; real Linux x64 download+35 titles verified.
- CLI `run` now also generates local session titles (`cli/run.py`: title thread runs alongside the turn, conditional replace after; skips resume and slash prompts). Test in `tests/cli/test_run.py`; Ruff/basedpyright green.
- Chat composer anchoring: `session-main` ResizablePanel needs `flex min-h-0 flex-col` on its inner wrapper so chat flex-1 fills the split height (otherwise input rises to content height). Repeated files/tasks/terminal toggles verified in Chromium at 1230×1388, 1440×900, 800×700; regression in SessionPage tests. 751 web tests, lint/typecheck/build passed.
- Release workflow tests: scope creation `--notes-file` lookup after `gh release create`; first occurrence belongs to draft refresh. Added executable missing/present changelog gate coverage; 23 workflow tests + full Python suite + Ruff lint/format + basedpyright passed.
- Follow-up delivery menu items: `items-start`→`items-center` so label/badge no longer hug the top edge (looked cropped). Lint forbids padding/gap on Button. Web tests/lint/types/build green.
- Released v0.53.0 (#407, PRs #402–#406); all validation green, Release run published PyPI + GitHub Release.
- Capped requires-python to >=3.12,<3.15 (PyYAML has no 3.15 Windows wheels → uv tool install failed needing MSVC); relocked.
- Released v0.54.0 (#409, PR #408 Python <3.15 cap); validation green, Release run published PyPI + GitHub Release.
- Dropped uvicorn[standard] → uvicorn + websockets==17.4 (removes pyyaml/uvloop/httptools/watchfiles) and removed <3.15 requires-python cap; regression test asserts uvicorn WS backend loads. Full suite (minus pre-existing failing test_lost_manager_lease_rejects_new_live_sessions, fails on clean tree) + Ruff/format/basedpyright green.
- Released v0.55.0 (#411, PR #410 plain uvicorn+websockets, no Python cap); validation green, Release run published PyPI + GitHub Release.
- Windows web terminal was untypeable (pipe-backed cmd.exe: no echo, `\r` not Enter). Now ConPTY via `pywinpty==3.1.2; sys_platform == 'win32'` (wheels cp312–cp315, amd64+arm64) in `web/terminal.py`; pywinpty `read()` returns `""` keep-alives, only `EOFError` = closed. Windows validation from WSL: `cd /mnt/c && cmd.exe /c 'set UV_PROJECT_ENVIRONMENT=%TEMP%\<venv>&& uv run --project \\wsl.localhost\Ubuntu\<repo> --directory <same> pytest ...'`. Terminal tests: 14 pass on Windows, 16 on Linux; Ruff/format/basedpyright green.
- Windows terminal review fixes: `_ConPty` in `web/terminal.py` uses pywinpty low-level `PTY` (not `PtyProcess`: its loopback relay leaks a `0011Ignore` marker); `WinptyError` is a plain `Exception` → wrapped to `OSError` so WS sends `{type:error}`; close = `taskkill /F /T` + `cancel_io()`; ConPTY startup emits `ESC[c` → stripped from scrollback; pipe fallback removed; WS `close` runs in `to_thread`. Terminal tests 18 pass on Windows, 17 on Linux.
- Released v0.56.0 (#413, PR #412 Windows ConPTY web terminal); validation green, Release run published PyPI + GitHub Release.
- Session titles in UI: `TruncatedText` (tooltip only when clipped; `transitionKey` fades in a changed title for the same session) used for sidebar rows and a collapsed-sidebar topbar breadcrumb (`WorkspaceBadge variant="text"` › title). Topbar is `@container` flex, breadcrumb gated on `@xl`/`@3xl` (not `md:`: right panels narrow the topbar while the viewport stays wide → overlap); lint forbids arbitrary grid templates; no `%` max-width inside the content-sized centre (collapses the label). Headless check: user's server on 7424 serves the rebuilt bundle; Playwright needs `executablePath` chromium_headless_shell-1248, run with `bun`, `waitUntil: "domcontentloaded"`. 754 web tests/lint/types/build green.
- Review fixes for session-title UI: `TruncatedText` clip check also compares fractional Range width (sub-pixel ellipsis), follows `:focus-visible` on the enclosing `a`/`button`, closes its tooltip on text change; callers pass `transitionKey` only once a real title exists (no "Untitled" → first-title animation); topbar uses `loadedSessionRecord` (not a `created_at` sentinel) and appends `› <sub-agent title>` on sub-agent routes. Left as is: breadcrumb a few px off-centre at mid widths (right controls wider than left), one Radix Tooltip per sidebar row. 761 web tests/lint/types/build + headless Chromium green.
- #169 kits (user decisions: name "kit", one-shot copy with no tracking/remove/update, core five parts, project-only): `kits/installer.py::install_kit` plans then applies; parts read from kit root or its `.agents/`; existing items kept unless `--force`; MCP servers merged by name into `.agents/mcp.json`; kit `AGENTS.md` appended between `<!-- kit:<name>:start/end -->` markers. CLI `kits add <source> [--list] [--force]`, docs `customization/kits.md`. 8 tests + Ruff/format/basedpyright/docs build green.
- `tests/test_mcp_pool.py::test_mcp_http_real_sdk_requests_and_cleanup[timeout:tools/call]` shortened the connect timeout to 0.1 s too; a GC pause in full-suite runs then dropped the healthy startup (failed 7/8 full runs once the kits test file was collected, 0 with `gc.disable()`). Now only the timeout under test is shortened. Full suite green 3/3. [verified 2026-11-12]
- #169 kits catalog: created public `pbi-agent/kits` (branch `main`; kits `coding`, `powerbi`, `research`, `customize` under `kits/<name>/` with `kit.json` description + `AGENTS.md`, copied from the skills/commands/agents catalogs — manual re-sync). Source with `kits/` dir = catalog; `kits add` lists default catalog, `--kit NAME` installs; `KitSelectionRequiredError` carries the listing. Live-verified list/install/overlap/force/tree-URL. Git over SSH fails on this host: clone/push via HTTPS with `-c credential.helper='!gh auth git-credential'`. [verified 2026-11-13]
