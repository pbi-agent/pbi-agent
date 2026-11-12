- [x] Include `/status` session usage dashboard (PR #392, merged 4998e974 on master after v0.51.0) in next release (v0.52.0)
- [x] Web terminal tab (PTY over WebSocket), Run-in-terminal for bash snippets, background-tasks icon → ActivityIcon
- [x] Web terminal: Windows now uses ConPTY via `pywinpty` (typing/echo/interactive prompts work)
- [x] Windows terminal review fixes: low-level pywinpty `PTY` backend (no loopback marker), errors reported to client, close kills process tree, ConPTY queries stripped from scrollback, bootstrap/`-i` for POSIX shells, no pipe fallback
- [ ] Web terminal on Windows: default shell is `COMSPEC` (cmd.exe), consider preferring PowerShell; confirm in a real browser on a Windows host
- [ ] CI is Ubuntu-only: ConPTY tests (`windows_only`) run only by hand; consider a `windows-latest` job for `tests/test_web_terminal.py`
- [x] Local session titles: background download of oot-oneliner GGUF + pinned official llama.cpp build at web start, generated title replaces first-message title (`session_titles.py`)
- [ ] Local session titles: verify on macOS and Windows hosts (only Linux x64 exercised end to end)
- [ ] Local session titles: no UI/status for download progress or opt-out besides `PBI_AGENT_LOCAL_TITLES=0`; CLI `run`, Telegram and runtime-created (`/new`) sessions still use truncated titles

- [x] Keep chat composer bottom-anchored when right-side panels open; regression tests for repeated files/tasks/terminal toggles and Chromium geometry checks at three viewport sizes.
- [x] Frontend validation for chat input anchoring: 751 web tests, lint, typecheck, build; browser confirms unchanged composer position across three viewport sizes.

- [x] Fix stale release-workflow notes ordering test; cover draft notes refresh and missing-file gate (23 workflow tests, Ruff lint/format, basedpyright passed).
- [x] Run full Python suite for release-workflow regression fix (passed).
