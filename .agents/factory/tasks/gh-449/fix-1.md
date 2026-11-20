# Fix: gh-449, round 1

fix: done

## Findings fixed
- [P3] Correct the claim that `web` never writes saved config.
  - `src/pbi_agent/cli/guides/pbi-agent.md:75` now says: saved configuration is written only by `pbi-agent config ...` commands and by the web UI Settings page (providers, model profiles, default profile, maintenance). It says that `run` and starting `web` only read the file, so the file can change while a web server is running.
  - `src/pbi_agent/cli/guides/config.md:7-12`: I kept "the only CLI path" (still true). I added that the web UI Settings page served by `pbi-agent web` writes the same file, and that `run` and starting `web` only read it.
  - Checked against the code: `src/pbi_agent/web/session/configuration.py` imports and calls `create_provider_config`, `create_model_profile_config`, `delete_*_config`, `select_active_model_profile` and `update_maintenance_config`.
  - I grepped all 56 guides for similar claims ("rewrite", "never write/modify", "only reads", "read-only"). No other guide says that `run` or `web` leaves the config unchanged. The remaining hits are accurate and are about specific read-only commands (`config providers list`, `config profiles list`, `config maintenance show`, `kanban list`, `usage-limits`).
- Conductor addition: `docs/environment.md:20` gave the `PBI_AGENT_REASONING_EFFORT` default as `xhigh` for OpenAI and `high` otherwise. I changed it to `medium`.
  - Checked against the code: `_default_reasoning_effort` in `src/pbi_agent/config.py:1807` ignores the provider kind and returns `"medium"`.
  - The page now matches `docs/cli.md:41`.
  - No other page under `docs/` or the guides still gives the old default.

## Files changed
- src/pbi_agent/cli/guides/pbi-agent.md
- src/pbi_agent/cli/guides/config.md
- docs/environment.md

## Validation
- `uv run pytest -q --tb=short -x tests/cli`: pass
- `uv run ruff check .`: all checks passed
- `uv run ruff format --check .`: 1039 files already formatted
- `bun run docs:build`: build complete
