- [x] Windows `pbi-agent upgrade` looks hung: run the deferred installer in its own console window (`src/pbi_agent/cli/upgrade.py`, `src/pbi_agent/self_update.py`)
- [-] Verify the new-console upgrade on a real Windows host: CREATE_NEW_CONSOLE launch + exit codes verified on Win11 26300 (default terminal = "let Windows decide"); still needs one visual check of tab vs window and the interactive key/Enter pauses
- [x] Don't block forever on `Read-Host` after a failed unattended upgrade (scheduled task, CI, remote session); only pause when interactive
- [x] Handle `$LASTEXITCODE` being `$null` when the installer can't start, so the window doesn't show a blank exit code and exit 0
- [x] Windows deferred path: check the installed version after exit 0 so a pinned install isn't reported as "finished"
- [x] Remove double quotes from the deferred `-Command` script (the failure `Write-Host`) so it doesn't depend on powershell.exe `\"` parsing
- [x] Keep installer warnings visible on success (5s, any key closes early; interactive only)
- [-] Guard against running `pbi-agent` while the deferred upgrade is replacing its files (only a docs note today; needs a cross-process lock design — a failed install now at least reports a non-zero exit in the window)
- [x] Test the deferred script's success branch and that `$code` is captured right after the installer call
- [-] Pre-existing on Windows: ~32 failing tests unrelated to upgrade (e.g. `tests/cli/test_catalogs.py::...test_main_config_profiles_crud_commands` — Rich truncates `analysis` at narrow console width; `test_web_serve.py`, `test_session_history.py`, `test_workspace_context.py`)

- [x] Inspect session `2efe3baaa161465a962190e6f1edbaef` read-only and confirm the assistant's link target
- [x] Open assistant workspace file links in the Explorer preview without navigating
- [x] Add regression tests and validate the bundled web app

- [x] Open web links from Markdown in a new tab without changing Explorer handling for workspace links
- [x] Rebuild the packaged frontend and pass type checking and lint
- [x] Verify link behavior in the full web test suite

- [x] Click saved web and workspace file links in real Chromium on the live app with `browser-use`

- [x] Evaluate /code-review findings on workspace file links; fix path:line, absolute workspace paths, extension-less relative links, sub-agent prefix, context churn, duplicated predicate
- [x] Run /verify on the live web UI (relative, path:line, absolute workspace path, LICENSE, external link)
- [x] Jump to and highlight the linked line range in the Explorer preview (`:42`, `:42-50`, `#L42`), incl. top-level `README.md:42` hrefs
