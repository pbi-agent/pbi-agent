# Project Goal

Provide a local CLI foundation for a Power BI editing agent with tool execution (including parallel tool calls) and report-template bootstrapping. All provider communication uses synchronous HTTP REST APIs via `urllib.request`:

| Provider | API Shape | Default Endpoint |
|---|---|---|
| **OpenAI** (default) | Responses API | `https://api.openai.com/v1/responses` |
| **xAI** | Responses API | `https://api.x.ai/v1/responses` |
| **Anthropic** | Messages API | `https://api.anthropic.com/v1/messages` |
| **Generic** (OpenAI-compatible) | Chat Completions API | `https://openrouter.ai/api/v1/chat/completions` |

## Running Tests

```bash
uv run pytest
uv run pytest tests/test_cli.py
uv run pytest tests/test_cli.py::DefaultWebCommandTests::test_main_defaults_to_web_for_global_options_only
uv run pytest -m slow
```

## Adding Tests

- Add new test modules under `tests/`.
- Name test files `test_*.py` so pytest discovers them automatically.
- Prefer pytest-style tests with plain `assert`; existing `unittest.TestCase` tests are still supported when needed.
- Import package code directly from `pbi_agent`; pytest is configured to add `src/` to `sys.path`, so new tests should not manually modify `sys.path`.
- Put shared fixtures in `tests/conftest.py` and use `@pytest.mark.parametrize(...)` for repeated input/output cases.
- Register any new custom markers in `pyproject.toml` under `tool.pytest.ini_options.markers` before using them.

Example:

```python
import pytest


@pytest.mark.parametrize(("value", "expected"), [("abc", 3), ("", 0)])
def test_string_length(value: str, expected: int) -> None:
    assert len(value) == expected
```

## Linting & Formatting

```bash
uvx ruff check . --fix && uvx ruff format .
```

## Project-Specific Tooling

```bash
uv run pbi-agent init --dest . --force
```

## Docs

- Documentation lives in `docs/` and is built with VitePress.
- Keep the GitHub Pages base path as `/pbi-agent/` in `docs/.vitepress/config.ts`.
- Validate docs changes with `npx vitepress build docs` or `npm run docs:build`.

## Code Review

Every pull request must be reviewed before merging. Reviewers should verify the
following:

1. **Correctness** – the implementation solves the stated problem and handles edge
   cases. Actively look for logic errors, off-by-one mistakes, and missing error
   handling.
2. **Clarity & simplicity** – code is easy to read and no more complex than
   necessary. Prefer small functions, descriptive names, and straightforward control
   flow.
3. **Performance** – avoid unnecessary allocations, redundant loops, or blocking
   calls that could degrade responsiveness. All HTTP communication must go through
   `urllib.request`.
4. **Test coverage** – every new feature includes tests and every bug fix adds a
   regression test. Changes to existing behaviour update the affected tests rather
   than removing them. Follow the conventions in *Adding Tests* above.
5. **Provider & tool coverage** – provider changes update the matching
   `test_<provider>_provider.py`; tool changes update `test_<tool>.py`.
6. **Lint & CI green** – `uv run pytest`, `uvx ruff check .`, and
   `uvx ruff format --check .` must all pass.
7. **Security** – no secrets, credentials, or unreviewed network calls.
8. **Minimal scope** – one concern per PR; unrelated changes go in separate PRs.

## Key Constraints

- Keep bundled PBIP template assets under `src/pbi_agent/report/`; packaging relies on `tool.hatch.build.targets.wheel.force-include`.
