# Repository Guidelines

## Project Structure & Module Organization

This repository targets a Python CLI coding agent dedicated to Power BI report creation and editing.

- `main.py`: current entry point (early scaffold).
- `pyproject.toml`: package metadata and runtime dependencies.
- `.env`: local secrets and API settings.

As features are added, organize code under `src/pbi_agent/`:

- `cli.py`: command routing and argument parsing.
- `agent/`: planning, tool orchestration, and prompt logic.
- `powerbi/`: report edit/create operations and validation helpers.
- `models/`: request/response schemas.
- `tests/`: unit and integration tests.

## Build, Test, and Development Commands

Use `uv` for local development.

- `uv sync`: install dependencies from `pyproject.toml` and `uv.lock`.
- `uv run python main.py`: run current CLI scaffold.
- `uv run python -m py_compile main.py`: syntax check.

When CLI modules are split into `src/`, prefer:

- `uv run python -m pbi_agent --help`: verify command surface.
- `uv run pytest`: run test suite.

## Coding Style & Naming Conventions

- Follow PEP 8 and 4-space indentation.
- Use `snake_case` for functions/modules, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Keep Power BI operations explicit: use names like `create_report`, `update_visual`, `validate_dataset_binding`.
- Add type hints on public functions and command handlers.
- Keep CLI I/O thin; place business logic in reusable modules.
- **Always run `uv run ruff format .` after modifying code to ensure consistent formatting.**

## Testing Guidelines

Use `pytest` with tests under `tests/`.

- File names: `test_*.py`; test functions: `test_*`.
- Cover command parsing, agent decision flow, and Power BI edit/create behaviors.
- Add negative tests for invalid report IDs, malformed edit payloads, and missing credentials.

## Commit & Pull Request Guidelines

- Write imperative commit subjects (example: `Add report layout update command`).
- Keep commits focused and reviewable.
- Reference issue/task IDs when available.

PRs should include:

- Problem statement and implemented approach.
- Commands run locally (for example, `uv run pytest`).
- Sample CLI usage/output for new commands.

## Security & Configuration Tips

- Keep secrets in `.env`; never commit tokens or tenant-specific secrets.
- Redact report IDs, workspace IDs, and auth headers from logs.
- Validate destructive edit operations with explicit confirmation flags in CLI commands.
