# Plan: Startup PyPI Update Warning

## Summary
Add/finish the CLI startup update warning by using the existing daily maintenance startup hook to check PyPI once per UTC day and render a Rich warning when a newer `pbi-agent` release exists. Keep the check best-effort and silent on network/API failures.

## Checklist
- [X] Keep `run_startup_maintenance()` as the only startup entry point, called from `pbi_agent.cli.entrypoint.main()` before command routing.
- [X] In `src/pbi_agent/maintenance.py`, preserve the existing daily claim policy (`maintenance_state` + UTC date): only the first process that claims daily maintenance runs the PyPI check; later runs that day skip it.
- [X] Keep the PyPI lookup on `https://pypi.org/pypi/pbi-agent/json` using `urllib.request`, a short timeout, JSON `Accept`, and `User-Agent: pbi-agent/<current-version>`.
- [X] Compare the PyPI `info.version` to `pbi_agent.__version__`; warn only when PyPI is strictly newer. Keep failures, malformed payloads, equal versions, and older versions silent.
- [X] Replace the plain `print(notice, file=sys.stderr)` with a small Rich renderer that writes to stderr, for example a yellow warning panel containing `pbi-agent <current> -> <latest>` and `uv tool install pbi-agent --upgrade`.
- [X] Keep `MaintenanceResult.update_notice` as a plain string for tests/diagnostics; add an optional-console rendering helper if needed for deterministic Rich tests.
- [X] Do not add config flags, DB schema changes, migrations, frontend/web UI warnings, or new dependencies.

## Public Interfaces / Types
- User-visible CLI behavior changes: a once-daily Rich-formatted stderr warning appears when PyPI has a newer `pbi-agent` version.
- No CLI arguments, config shape, FastAPI contract, persisted schema, provider/tool interfaces, or frontend types change.
- Internal helper functions in `pbi_agent.maintenance` may be added/refined for rendering and tests.

## Test Plan
- [X] Update `tests/test_maintenance.py` so daily maintenance asserts the update check runs once per day and the Rich warning is emitted only on the first run.
- [X] Add/adjust coverage for the rendered warning content: title/wording, current version, latest version, and exact upgrade command `uv tool install pbi-agent --upgrade`.
- [X] Keep/update version comparison tests for newer, equal, and older PyPI versions.
- [X] Mock `urllib.request.urlopen` or `_latest_pypi_version()` in tests; no test should require network access.
- [X] Validate with `uv run pytest -q --tb=short -x tests/test_maintenance.py` and at least one CLI entrypoint-focused suite such as `uv run pytest -q --tb=short -x tests/cli/test_entrypoint.py`.
- [X] Run Python quality checks for the touched surface: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run basedpyright`.

## Validation Notes
- Passed: `uv run pytest -q --tb=short -x tests/test_maintenance.py`.
- Passed: `uv run pytest -q --tb=short -x tests/cli/test_entrypoint.py`.
- Passed: `uv run ruff check .`.
- Passed: `uv run ruff format --check .` after formatting touched files with `uv run ruff format src/pbi_agent/maintenance.py tests/test_maintenance.py`.
- Passed: `uv run basedpyright`.
- Final gate passed: `uv run ruff check .`, `uv run ruff format --check .`, `uv run basedpyright`, and `uv run pytest -q --tb=short -x`.

## Assumptions / Scope
- “Once a day” means the repository’s existing maintenance policy: one successful daily claim per UTC date in the internal session DB.
- The warning should appear for any CLI startup path, including `web`, because the maintenance hook runs before command-specific routing.
- PyPI/network failures must never block startup or print noisy errors; only an actual newer version produces the Rich warning.
- The required suggested command is exactly `uv tool install pbi-agent --upgrade`.
