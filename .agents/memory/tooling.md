# Tooling, validation, tests, releases

Migrated from `MEMORY.md` on 2026-11-07; entries predate verification tags.

- Ruff: rules `E4/E7/E9/F`,`I`,`UP`,`B`,`RUF`,`PLW1510`; ignore B009/B010 (deliberate dynamic getattr/setattr). Use explicit `check=False`, targeted noqa only. Ruff Markdown formatting on.
- Tooling pins: Bun 1.4.4 (workflows/`packageManager`/`test_workflows`); `web:build` = `bun --bun vite build` (Node-run Vite gives different chunk hashes → CI static-asset drift). Deps: mcp 2.x (httpx2; streamable_http yields 2-tuple; timeout sends `notifications/cancelled`), pytest 9.2 (coordinator `__delattr__` forwards for monkeypatch undo).
- Test hygiene: uploads in `tmp_path / "web_uploads"`; gate worker drain with explicit events, no sleep polling. Vitest 4 mocks need concrete `Mock`/`MockInstance` types. Browser UI testing works via headless Playwright + apt-extracted nss/nspr/asound libs on local build.
- Releases: latest v0.48.0. Release commit includes `uv.lock` from `uv lock` (user decision 2026-11-08). Plain `/release` authorizes minor push/merge/publish unless narrowed; post-PR history rewrite needs approval. Use `release-writing`, `docs/changelog/index.md`, `docs/changelog/v<version>.md`. `release.yml` publishes PyPI + GitHub Release; retry `gh workflow run release.yml --ref master -f version=<current-version>`; manual dispatch after merge-push publish skips unchanged version (expected). Never rerun old-SHA release. Workflow copies VitePress frontmatter into GitHub notes → strip after publish. PyPI CDN lags (JSON ~5 min+); verify, don't republish.
- Upgrade: `pbi-agent upgrade`/`update`; `self_update.py` detects uv tool/pipx/venv pip, refuses PEP 610 source installs; `--check` exits 0/100/1. Windows path unit-tested only.
- Security: open packaging follow-up — transitive security minima are lock-only, not enforced in published runtime metadata.
- Linux browser open: stdlib `webbrowser.open` in `-I` child, DEVNULL stdio, bounded wait; Snap Brave GPU/AppArmor logs are browser noise. GUI launch unverified.
- `shadcn add` may emit `import { cn } from "cn"` (resolves via `@shadcn/lint` dep); rewrite to `@/lib/utils`. Build static assets with the CI-pinned Bun (1.4.4; local upgraded) or the CI static-asset check drifts. [verified 2026-11-07]
