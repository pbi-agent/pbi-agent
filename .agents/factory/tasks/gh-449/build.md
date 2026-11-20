# Build: gh-449, integrated `--doc` guides for every pbi-agent CLI path

build: checks-pass

## Changed files (task-scoped, for staging)
- `src/pbi_agent/cli/doc.py` (new, about 105 lines): `iter_parser_paths`, `guide_filename`, `load_guide`, `DocAction`, `attach_doc_options`, `DOC_HELP`, `ROOT_DOC_HELP`. Imports only stdlib.
- `src/pbi_agent/cli/parser.py` (+12/-1): imports `attach_doc_options`, calls it just before `return parser`, adds one sentence to the root epilog, adds `"--doc"` to the no-default-insertion token set in `_default_command_insertion_index`. ruff format wrapped that set over several lines.
- `src/pbi_agent/cli/guides/*.md` (new, 56 files, 3,243 lines). Names are exactly as in plan.md: `pbi-agent.md`, `run.md`, ..., `config.profiles.select.md`. There is no `__init__.py`.
- `tests/cli/test_doc.py` (new, about 500 lines, 308 test cases).
- `docs/cli.md` (+23/-6): the `--doc` sentence at line 8, a new `## Built-in Guides (\`--doc\`)` section before `## Global Options`, and minimal fixes where the docs were wrong against the code (listed below).

Stage these with: `git add src/pbi_agent/cli/doc.py src/pbi_agent/cli/parser.py src/pbi_agent/cli/guides tests/cli/test_doc.py docs/cli.md`

`entrypoint.py`, `cli/__init__.py`, `pyproject.toml` and the existing tests are unchanged.

## What changed
- **Mechanism.** `DocAction` uses `nargs=0` and `dest`/`default` of `SUPPRESS`, so it never appears on the Namespace. It prints the packaged guide to `sys.stdout` with exactly one trailing newline, with no colors and no pager, then calls `parser.exit(0)` during `parse_args`. That happens before required-arg checks, startup maintenance, the PyPI check, `load_dotenv`, config resolution and server start. If a guide is missing it calls `parser.exit(1, "pbi-agent: no --doc guide found for `<prog>`.")`.
- **Attachment.** `attach_doc_options` runs once on the finished tree, so the `channels` subtree from `channels.py` is covered. Aliases are deduped by parser identity, so `update` shares `upgrade`'s parser and guide.
- **Default command.** `pbi-agent --doc` and `pbi-agent --verbose --doc` are no longer rewritten to `... web`.
- **Guides.** Every guide follows the plan template and uses the exact section headings. The worker wrote the root guide. Six sub-agents wrote the command groups (run/web/sandbox; init/upgrade/sessions/hooks; kanban/channels; skills/commands/agents/kits; config/maintenance/profiles; config providers), each reading the parser and handler code for its group. Several of them ran their commands against throwaway HOME, config and auth stores in the scratchpad to confirm exit codes and messages. The worker reviewed a sample for voice and accuracy: root, `run`, `web`, `config providers create`, `config providers delete`, `channels telegram`. Lengths: leaves and parents are 41-82 lines, root is 154. All guides are ASCII.
- **`docs/cli.md` minimal fixes (code wins):**
  - Line 11: the tip said `pbi-agent --api-key ...` launches the browser UI. In fact runtime flags are rejected for the implicit `web` (exit 2). The example now uses `pbi-agent --verbose`, and a note about the rejection is added.
  - Global Options table: the `--reasoning-effort` default was `xhigh` for OpenAI and `high` otherwise. The code (`config.py` `_default_reasoning_effort`) returns `medium`.
  - Providers create/update rows: `xai_account` was added to the `--auth-mode` choices (the parser accepts it).
  - Image Input Support: formats are now listed as PNG/JPEG/WEBP/HEIC/HEIF, detected from content, with a 20 MB limit (`media.py`). Before, it listed extensions only.

## Acceptance criteria -> evidence
| AC | Evidence |
| --- | --- |
| 1 `--doc` at root and every path, non-empty Markdown, exit 0 | `test_tree_has_expected_paths` (56 paths), `test_doc_prints_guide_and_exits_zero[*]` (56 cases through `cli.main`, stdout == guide, starts `# pbi-agent`, empty stderr, maintenance patched to raise), `test_update_alias_prints_upgrade_guide`, `test_argv_with_default_command_keeps_root_doc`. Smoke runs in a fresh HOME: `--doc`, `run --doc`, `web --doc`, `config providers create --doc`, `update --doc` all exit 0 and print Markdown. |
| 2 no command without a guide | `test_every_parser_has_one_doc_action`, `test_every_path_has_guide`, `test_no_orphan_guides`, and `test_guard_flags_new_subparser_without_guide`: a fake `zz-undocumented` subparser is flagged by the guard, and its `--doc` exits 1 with the "no --doc guide" message. The guard test uses its own tree walk, not `iter_parser_paths`. |
| 3 `run`/`web`/`config providers create --doc`: no args, no config, no side effects | `test_doc_has_no_side_effects[*]`: in-process, with maintenance, `resolve_runtime`, `resolve_web_runtime`, `configure_logging`, the run/web/config handlers, `load_dotenv`, `urllib.request.urlopen` and `socket.create_connection` all patched to raise. It asserts exit 0 and an unchanged `tmp_path` and cwd. `test_doc_subprocess_matches_help_side_effects[*]`: in a real subprocess with a fresh HOME, no `PBI_AGENT_*` or `*_API_KEY` vars, and an empty cwd, it asserts rc 0, Markdown, empty stderr, no `config.json`, an empty cwd, and the same files created as `--help` creates. Smoke `find $HOME -type f` shows only `.pbi-agent/sessions.db` from pbi-agent; the `.cache/uv` files come from uv itself. Creating `sessions.db` at import time matches what `--help` already does, and the human accepted this at triage. |
| 4 guide content | `test_guide_has_required_sections[*]` (exact ordered headings, H1 `# pbi-agent <path>`, non-empty sections, ASCII, no ANSI, no trailing `\`), `test_parent_guide_lists_children[*]` (each child plus its `--doc` pointer), `test_root_guide_indexes_every_command` (all 55 paths plus `update`), `test_upgrade_guide_mentions_update_alias`, `test_guide_documents_every_option[*]` (every visible option and positional), `test_guide_examples_parse[*]` (every `pbi-agent` line in a bash block parses with the real parser, no exit 2). A sample was also reviewed by hand against the code. |
| 5 root and command `--help` mention `--doc` | `test_help_mentions_doc[*]` (56 cases: the `[--doc]` usage token and the `--doc` row for commands; the row plus the `pbi-agent --doc` epilog for the root). Smoke: `--help \| grep -- --doc` gives 3 lines, and `run --help` shows `[--doc]` and the row. |
| 6 docs site | `docs/cli.md` line 8 sentence and the `## Built-in Guides (\`--doc\`)` section (behavior, help-like precedence, root not `web`, aliases, placement, `--d` note, examples). `bun run docs:build` passes. |
| 7 behavior and `--help` unchanged apart from `--doc` | The help dump diff (below) has 0 unexpected hunks. All existing `tests/cli` pass unmodified (478 including the new file), and the full suite passes. |
| profile `acceptance_tests` | This table. |
| profile `docs` | The `docs/cli.md` change plus `bun run docs:build` passing. |

## Help diff summary (AC7)
Scratch files are in `/tmp/claude-1000/-home-drod-workspace-pbi-agent/3740159b-c9bb-4d38-9ce8-daf36aa11bcc/scratchpad/gh-449/`:
- `dump_help.py` walks `build_parser()` with the terminal width patched to 120.
- `help-before.txt` was taken before any edit; `help-after.txt` after.
- `help.diff` is the diff; `check_diff.py` is the hunk checker.

Results:
- 56 parser help texts were compared. The diff has 55 removed lines and 113 added lines.
- `check_diff.py` removes the `--doc` options row, the ` [--doc]` usage token and the new epilog sentence, normalizes whitespace, and compares each parser's help to the baseline. Result: `sections 56 unexpected 0`.
- Changes seen:
  - `[--doc]` in every command usage line. In `sandbox` it is wrapped onto its own line.
  - One `--doc` row in each `options:` block.
  - The root epilog sentence, which re-wraps to two lines.
  - Nothing else.

## Validation
| command | result |
| --- | --- |
| help dump before/after + `check_diff.py` | pass (0 unexpected) |
| `uv run pytest -q --tb=short -x tests/cli/test_doc.py` | pass (308 passed) |
| `uv run pytest -q --tb=short -x tests/cli` | pass (478 passed) |
| `uv run pytest -q --tb=short -x` (full) | pass (2413 passed, 9 skipped, 59s) |
| `uv run ruff check .` | pass |
| `uv run ruff format --check .` | pass (1037 files already formatted) |
| `uv run basedpyright` | pass (0 errors, 0 warnings) |
| `bun run docs:build` | pass |
| `uv build --out-dir <scratch>/dist` + zip/tar check | pass: wheel has 56 `pbi_agent/cli/guides/*.md`, sdist has 56 `src/pbi_agent/cli/guides/*.md` (the files are still untracked; hatchling includes them anyway) |
| smoke (fresh HOME, empty cwd) | pass: see the AC1/AC3/AC5 rows |

No frontend checks were run, because `webapp/` is not touched.

## Assumptions
- **Test design:**
  - The `pyproject.toml` `addopts` already sets `-q -x`. The plan's validation commands were run as written; `-o addopts=""` was used only to read the totals.
  - `test_guide_examples_parse` cuts each example line at the first shell operator (`|`, `>`, `&&`, `;`, ...) and skips `VAR=value` prefixes.
  - `test_guide_documents_every_option` checks the longest option string. The guides list all aliases in one backtick span.
- **Guard test:** it builds the parser with `attach_doc_options` patched out, adds the fake subparser, then calls `attach_doc_options` on the whole tree. This avoids attaching `--doc` twice.
- **Root `--doc` help text:** `ROOT_DOC_HELP` sits in the root `options:` block next to `-v/--version`, because a post-build `add_argument` lands in the default group.
- **Out-of-scope gaps:** gaps in `docs/cli.md` (no sections for sessions, hooks, channels or maintenance; missing profile options; no `usage-limits` row; no `skills enable/disable`) were left alone, as the plan says. `docs/environment.md` has the same outdated `PBI_AGENT_REASONING_EFFORT` default (`xhigh`/`high` vs `medium` in the code). It was not edited, because the plan limits doc fixes to `docs/cli.md`.

## Findings worth a follow-up (not changed; out of scope)
- `config providers` auth errors are not caught. Examples: `auth-refresh` with no session, `auth-import` on an `api_key` provider, network failures. They end with a Python traceback and exit 1 instead of `Error: ...` and exit 2. The guides describe the current behavior.
- `hooks --project-dir X trust KEY`: the parent-level `--project-dir` is silently replaced by the subparser default `.`. The guides document that it must come after the action.
- `sandbox run --session-id` probably fails, because the session's host directory is not mounted at that path in the container. A guide pitfall covers it; it was not verified in Docker.
- Session directories are stored lowercased. On case-sensitive filesystems, `run --session-id` may fail for workspace paths with uppercase letters. A pitfall covers it.
- The `--allowed-tools` help in `parser.py` lists `read`, which is a legacy alias of `read-image`.

## Unrelated dirty files (not touched)
`.agents/agents/operator.md`, `.agents/commands/factory.md`, `MEMORY.md`, `TODO.md`, and `.agents/factory/tasks/` (except this `build.md`) were modified or untracked before this stage and were left as they were.
