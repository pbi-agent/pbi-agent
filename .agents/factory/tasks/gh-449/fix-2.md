# Fix: gh-449, round 2 (code-quality fix round 1)

fix: done

## Finding fixed
- [major] Make the guide-to-parser sync guard bidirectional (`tests/cli/test_doc.py:316`, quality-1.md).
  - New reverse check `test_guide_names_only_existing_options` (parametrized over all 56 paths). It collects every `-x` / `--flag` token from the Usage section (fenced lines) and from the Options section (inline backtick spans). The root guide uses Global options instead of Options. Each flag must exist on its parser, an ancestor, or the root (`_flags_on_path`).
  - Cross-references are checked against the command they name. A span that starts with `pbi-agent` is resolved through the real subparser choices (aliases included, so `pbi-agent update` resolves to `upgrade`). Its flags are then checked against that command's parser chain. For example, `pbi-agent web --port` in `channels telegram restart` is checked against `web`, and `pbi-agent hooks --json` is checked against `hooks`. This is stricter than allowing any name: a cross-reference to a flag that was removed elsewhere also fails.
  - Allowlist `FOREIGN_FLAGS` has one commented entry, `("sandbox",): {"-e"}`, which is pip's flag (`pip install -e`). The comment limits the list to flags of other programs.
  - New `test_guide_usage_matches_argparse` (56 paths) compares the first Usage line of each guide with `parser.format_usage()`. Both sides go through the same `_usage_skeleton` normalizer, which gives the ordered list of option names and positionals, with optional items as `[name]`. The normalizer removes:
    - the `[GLOBAL OPTIONS]` and `[SANDBOX OPTIONS]` prefixes;
    - metavars, because some guides deliberately shorten them (`config providers create --kind KIND` against the argparse choices list, `--api-key KEY` against `PROVIDER_API_KEY`);
    - subcommand placeholders (`<action> ...`, `[<command> ...]`, `<scope> <action> [OPTIONS ...]`);
    - argparse's `[-h]` and `[--doc]`.
    The root guide's first line must also match the custom root usage string exactly. Later Usage lines are skipped on purpose: the `update` alias line, the root `--doc` line and the `hooks <action>` summary. Their flags are still covered by the reverse flag check.
  - Why a skeleton and not an exact string match: an exact match would fail for the 14 known intentional differences plus the metavar renames. The skeleton still catches added, removed or renamed options and positionals, a change of order, and an optional/required change. It is independent of terminal width: whitespace is collapsed before parsing. I checked that the skeleton is identical at widths 40, 80, 120 and 1000 (153 items across 56 parsers). The test also pins width with the existing `wide_terminal` fixture.
  - `test_stale_option_check_flags_removed_option` is a permanent regression test. It feeds an `init` guide with stale flags in Usage and Options and asserts that both are reported. It also asserts that out-of-scope sections are ignored.

## Per-mismatch decision (the 6 from quality-1.md)
| path | token | decision | evidence |
| --- | --- | --- | --- |
| `sandbox` | `-e` | Allowlisted as a foreign flag. The guide is correct. | Span is `pip install -e`. `src/pbi_agent/cli/sandbox.py:266` runs `python -m pip install ... -e` for `--local-source`. It is not a pbi-agent flag. |
| `hooks trust` | `--json` | Ancestor or cross-reference. The guide is correct. | Span is `pbi-agent hooks --json`. `--json` is defined on the `hooks` parent (`parser.py:524`), and `cli/hooks.py:102` emits `"key"`. |
| `hooks enable` | `--json` | Same as `hooks trust`. | Same. |
| `hooks disable` | `--json` | Same as `hooks trust`. | Same. |
| `channels telegram` | `--token-env-var`, `--token-secret` | The guide was misleading, so I fixed the guide. | These flags exist only on the child `channels telegram configure` (`cli/channels.py:99,104`). The `channels telegram` parser accepts neither, and its Options section says "No options besides `-h/--help` and `--doc`". The bare mentions read as parent options. They now say `pbi-agent channels telegram configure --token-env-var` / `--token-secret`, and the check validates them against `configure`. |
| `channels telegram restart` | `--port` | Cross-reference. The guide is correct. | Span is `pbi-agent web --port`, which documents the shared default 7424 used by `--web-port` (`cli/channels.py:137,240`). It resolves to `web`, where `--port` exists. |

## Files changed
- tests/cli/test_doc.py: reverse flag check, foreign-flag allowlist, Usage skeleton comparison, and a regression test for the check.
- src/pbi_agent/cli/guides/channels.telegram.md: token flag mentions now name `configure`.

## Validation
- `uv run pytest -q --tb=short -x tests/cli`: 591 passed (`tests/cli/test_doc.py`: 421 passed).
- `uv run ruff check .`: all checks passed.
- `uv run ruff format --check .`: 1042 files already formatted.
- `uv run basedpyright`: 0 errors, 0 warnings, 0 notes.
- Before the guide fix, the new check failed on exactly `pbi-agent channels telegram --token-env-var` / `--token-secret`. That confirms it detects real drift.
- Deliberate stale flag demo (temporary edit; I restored the originals from a scratch backup and checked them with `cmp`):
  - I added `` - `--zz-stale`: removed flag. `` to the Options of `kanban.list.md`. Result: FAILED `test_guide_names_only_existing_options[pbi-agent kanban list]` (`['pbi-agent kanban list --zz-stale'] != []`).
  - I removed `[--show-steps]` from the Usage line of `sandbox.run.md`. Result: FAILED `test_guide_usage_matches_argparse[pbi-agent sandbox run]`.
  - All other tests passed in that run (2 failed, 110 passed).
