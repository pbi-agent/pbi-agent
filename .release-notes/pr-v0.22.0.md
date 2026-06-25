## Summary

Release v0.22.0 ships Telegram channel integration, xAI subscription auth, channels CLI, `/new` session command, Telegram Markdown outbound formatting, and shell output compression via `codetool-shell` 0.1.3.

## Highlights

### Added
- Telegram channel MVP with workspace-scoped settings and session routing
- Settings → Channels UI and `pbi-agent channels` CLI
- xAI OAuth subscription authentication
- `/new` command for fresh web sessions

### Changed
- Telegram outbound Markdown entity formatting
- Default shell stdout/stderr compression

### Fixed
- Pinned `httpx2` / `httpcore2` test client stack

## Changelog

Full changelog: [docs/changelog/v0.22.0.md](docs/changelog/v0.22.0.md)

## Validation

- `uv run ruff check .` — pass
- `uv run ruff format --check .` — pass
- `uv run basedpyright` — pass
- `uv run python scripts/dead_code.py` — pass
- `uv run pytest -q --tb=short -x` — pass
- `bun run docs:build` — pass

## Excluded

- Unrelated local edit: `.agents/commands/release.md` (not staged)
- Session `TODO.md` bookkeeping (not in release commit)