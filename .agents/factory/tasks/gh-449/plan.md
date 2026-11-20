# Plan: gh-449, integrated `--doc` guides for every pbi-agent CLI path

plan: ready

## Summary
A `DocAction` (an argparse Action with `nargs=0` that prints and exits, the same pattern `-h` and `-v` use) is attached to all 56 parsers. One post-build walk at the end of `build_parser()` attaches it, which also covers the `channels` subtree built in `channels.py`. When it fires, it prints a packaged Markdown guide from `src/pbi_agent/cli/guides/` and exits 0 during `parse_args`. That happens before required-arg errors, startup maintenance, the PyPI check, `.env` loading, config resolution and server start, so AC3 holds by construction. The human accepted the import-time `~/.pbi-agent/sessions.db` creation as `--help` parity at triage; it is out of scope.

Facts confirmed in this pass:
- The walk gives 56 parsers: the root plus 55 paths. `update` is the only alias and shares the `upgrade` parser object.
- A scratch prototype confirmed that `run --doc`, `kanban --doc`, `config providers create --doc` and `update --doc` all exit 0.
- Today `_argv_with_default_command(parser, ["--doc"])` returns `["--doc", "web"]`. The fix below makes it return `["--doc"]`.
- `uv build` places non-Python package files, including subdirectories without `__init__.py` (`web/static/app/**`, `models/model_catalog.json`, `sandbox/Dockerfile.sandbox`), in both the wheel and the sdist. **No `pyproject.toml` change is needed.**
- Baseline: `uv run pytest tests/cli` passes and `bun run docs:build` passes.

## Key changes

### 1. Mechanism (new `src/pbi_agent/cli/doc.py`, small edit in `parser.py`)
- `doc.py` imports only stdlib (`argparse`, `importlib.resources`, `sys`, `collections.abc`). It must not import `parser.py`, to avoid an import cycle. It contains:
  - `iter_parser_paths(parser) -> Iterator[tuple[tuple[str, ...], ArgumentParser]]`: depth-first over `argparse._SubParsersAction.choices`, deduped by `id(subparser)` so aliases map to their target. It yields `((), root)` first.
  - `guide_filename(path)`: `"pbi-agent.md"` for `()`, otherwise `".".join(path) + ".md"` (examples: `run.md`, `config.providers.auth-status.md`). Command tokens never contain `.`, so the scheme is unambiguous.
  - `load_guide(path) -> str | None`: `importlib.resources.files("pbi_agent.cli").joinpath("guides", guide_filename(path))`. Returns `None` when the file is missing. Reads with `encoding="utf-8"`.
  - `class DocAction(argparse.Action)`. Constructor: `(option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None, *, guide_path: tuple[str, ...] = ())`, with `nargs=0`. Using `SUPPRESS` means `args.doc` never appears on the namespace, so existing Namespace checks stay unchanged. `__call__` does this:
    - If the guide is found, it writes it to `sys.stdout` (looked up at call time, so tests can patch it) with exactly one trailing newline. No colors and no pager. Then `parser.exit(0)`.
    - If the guide is missing, it calls `parser.exit(1, f"pbi-agent: no --doc guide found for `{parser.prog}`.\n")`. Tests prevent this from happening in a release.
  - `attach_doc_options(root)`: for each `(path, p)` from `iter_parser_paths`, calls `p.add_argument("--doc", action=DocAction, guide_path=path, help=ROOT_DOC_HELP if not path else DOC_HELP)`.
    - `DOC_HELP = "Print the long-form Markdown guide for this command and exit."`
    - `ROOT_DOC_HELP = "Print the long-form Markdown guide to pbi-agent and all commands, then exit."`
    - Neither text contains ` console ` or ` open ` (protects `test_parser.py:124-128`).
- `parser.py` changes:
  - Call `attach_doc_options(parser)` immediately before the final `return parser` (currently line 1203). Adding it last puts `[--doc]` after all existing optionals in each usage line, so `usage: pbi-agent web [-h] [--host HOST] [--port PORT]` (`test_parser.py:109`) still matches. The row lands in the default `options:` group.
  - At line 1229, add `"--doc"` to the `{"-h", "--help", "-v", "--version"}` set, so `pbi-agent [global opts] --doc` is not rewritten to `... web`.
  - Root epilog becomes: "Run `pbi-agent <command> --help` for command-specific options. Run `pbi-agent --doc` or `pbi-agent <command> [<subcommand> ...] --doc` for a long-form Markdown guide. Defaults to `web` when no command is provided."
  - No other help text changes. Command parsers get no epilog: their `--help` mentions `--doc` through the `[--doc]` usage token and the `--doc` options row (this satisfies AC5 at command level).
- `entrypoint.py` and `cli/__init__.py` stay unchanged. No export changes, so `test___init__.py` is unaffected.
- Accepted `--help` diff, prototyped: a `[--doc]` token in the usage line (before positionals), a re-wrap where the line overflows (only `sandbox` today; `[--doc]` moves to its own line), one `--doc` options row, and the root epilog sentence. Nothing else.
- Known accepted pitfall: subparsers keep `allow_abbrev=True`, so `--d` becomes ambiguous for `web`/`sandbox web` (`--dev`), `sandbox` (`--detach`) and `channels telegram configure` (`--disable`). `kanban create --d` was already ambiguous. No `--do*` option existed before. Document this in the docs and in the affected guides' Pitfalls sections. Do not change `allow_abbrev`.

### 2. Guide content (`src/pbi_agent/cli/guides/*.md`, 56 files, git-tracked package data)
Files (exactly these names):
- Root and top-level: `pbi-agent`, `run`, `init`, `upgrade`, `web`, `sessions`.
- `sandbox`, `sandbox.web`, `sandbox.run`.
- `hooks`, `hooks.trust`, `hooks.enable`, `hooks.disable`.
- `kanban`, `kanban.create`, `kanban.list`.
- `channels`, `channels.show`, `channels.telegram`, `channels.telegram.show`, `channels.telegram.configure`, `channels.telegram.restart`.
- `skills`, `skills.list`, `skills.enable`, `skills.disable`, `skills.add`.
- `commands`, `commands.list`, `commands.add`.
- `agents`, `agents.list`, `agents.add`.
- `kits`, `kits.add`.
- `config`, `config.maintenance`, `config.maintenance.show`, `config.maintenance.set`.
- `config.providers`, `config.providers.{list,create,update,delete,auth-status,auth-login,auth-import,auth-refresh,auth-logout,usage-limits}`.
- `config.profiles`, `config.profiles.{list,create,update,delete,select}`.

Each name gets a `.md` suffix. Do not add an `__init__.py` to `guides/`.

**Template.** Plain ASCII Markdown: no em dashes, smart quotes, arrows or emoji, because Windows consoles may not encode them. No ANSI escape codes. No line ends with `\`. Headings must match the exact text below, because tests match them.
- Command and subcommand (leaf):
  - H1 `# pbi-agent <path>`, then a one- or two-sentence summary.
  - `## Purpose`: what it does and when to use it, versus the alternatives.
  - `## Usage`: a ```text block with the synopsis, mirroring the argparse usage line minus `-h`/`--doc`.
  - `## Options and arguments`: one bullet per visible option or positional. Format: ``- `-p, --prompt PROMPT` (required): ...``, giving the default, choices, env var and interactions. If there are none: "No options besides `-h/--help` and `--doc`."
  - `## Examples`: ```bash blocks with realistic invocations, one command per line, `#` comments allowed.
  - `## Workflows`: two or three numbered multi-step flows that combine commands.
  - `## Related commands`: bullets with ``- `pbi-agent <path>` `` and why it is related.
  - `## Pitfalls`: constraints and common errors (exit codes, required config, workspace/cwd assumptions, abbreviation notes where they apply).
- Parent command: the same sections, plus `## Subcommands` right after `## Usage`. It has one bullet per child: ``- `pbi-agent <path> <child>`: summary. Guide: `pbi-agent <path> <child> --doc`.`` It also states what happens when no subcommand is given: an error for the required ones, a default for `sandbox` (`web`) and `hooks` (list).
- Root `pbi-agent.md`:
  - `# pbi-agent`.
  - `## Overview`: what pbi-agent is, the providers, and that `web` is the default command.
  - `## Usage`.
  - `## Global options`: every visible root option, grouped like `--help` (Provider and API, Model behavior, Runtime and resilience, Diagnostics, plus `-v/--version`). Mention hidden API-key aliases only in one sentence.
  - `## Settings resolution`: CLI flags, then `PBI_AGENT_*` env, then provider-specific env, then saved providers/profiles in `~/.pbi-agent/config.json`, then defaults. Also cover `.env` loading, that `--profile-id` is applied before explicit overrides, and that `web` uses saved web settings and rejects runtime provider/model flags.
  - `## Commands`: an index listing every one of the 55 paths as `` `pbi-agent <path>` `` with a one-line summary, nested by group, and noting the `update` alias.
  - `## Examples`.
  - `## Getting more detail`: the drill-down with `pbi-agent <command> [<subcommand> ...] --doc`, plus `--help`. Put `--doc` last, after the deepest command name. `pbi-agent --doc run` prints the root guide.
  - `## Pitfalls`.
- Alias: `upgrade.md` states that `pbi-agent update` is an alias with the same guide.
- Length targets: leaf 30-70 lines, parent 40-90, root 120-200 (about 3,000 lines in total). No padding: a short, accurate section is better than filler.

**Source of truth.** Code wins. `docs/cli.md` must not be contradicted. Before writing each group, the worker reads:
| guides | read |
| --- | --- |
| root | `cli/parser.py` (global options), `cli/entrypoint.py` (routing, `--mcp`/`--agents`, web flag rejection), `config.py` (`resolve_runtime`/`resolve_web_runtime`), `maintenance.py`, `docs/cli.md` Global Options, `docs/environment.md`, `docs/providers.md` |
| run, web, sandbox.* | `cli/run.py`, `cli/web.py`, `cli/sandbox.py`, `pbi_agent/sandbox/`, `docs/cli.md`, `docs/sandbox.md`, `docs/web-ui.md` |
| init, upgrade, sessions | `init_agents.py`, `cli/upgrade.py`, `cli/sessions.py`, `docs/cli.md` |
| hooks.* | `cli/hooks.py`, `pbi_agent/hooks/`, `docs/customization/hooks.md` |
| kanban.* | `cli/kanban.py`, `docs/kanban-dashboard.md`, `docs/cli.md` |
| channels.* | `cli/channels.py`, `pbi_agent/channels/` |
| skills/commands/agents/kits.* | `cli/catalogs.py`, `docs/customization/{skills,commands,sub-agents,kits}.md`, `docs/cli.md` |
| config.* | `cli/config.py`, the `config` block in `parser.py`, `docs/model-profiles.md`, `docs/providers.md`, `docs/cli.md` |

Process:
- Write group by group in the order of the table.
- After each group, run `uv run pbi-agent <path> --help` for each path in it and the `tests/cli/test_doc.py` suite.
- If the worker delegates guides to sub-agents, use one group per sub-agent and pass it this template and its table row. The worker then reviews them for a consistent voice.
- If a guide would contradict `docs/cli.md` because the docs are wrong against code, fix that `docs/cli.md` line minimally and record it in `build.md`. Do not add new `docs/cli.md` sections for commands it does not yet cover (sessions, hooks, channels, maintenance); that is out of scope.

### 3. Docs site (`docs/cli.md`)
- Line 8: keep the `-h/--help` sentence and add one: "`--doc` is available at the same levels and prints a long-form Markdown guide."
- Add a `## Built-in Guides (\`--doc\`)` section after the existing tip and before `## Global Options`. It covers:
  - the behavior: root and every subcommand at any depth, plain Markdown to stdout, no colors or pager, exit 0;
  - `--help`-style precedence: missing required args are ignored, no server/provider/config/network side effects, works without saved config or API keys;
  - `pbi-agent --doc` prints the root overview, not `web`;
  - aliases (`update`) show their target's guide;
  - put `--doc` after the deepest command name;
  - the `--d` abbreviation note;
  - an examples block (`pbi-agent --doc`, `pbi-agent config providers create --doc`, `pbi-agent run --doc > run-guide.md`).
- Keep `<command>`-style placeholders inside backticks or code blocks, because VitePress parses raw `<tags>` and `{{ }}` as Vue.

## Test plan (new `tests/cli/test_doc.py`, pytest style; existing test files untouched)
The test builds its own walk (recursing through `_SubParsersAction.choices`, deduping by `id`) instead of reusing `iter_parser_paths`, so the guard does not confirm itself. It gets `EXPECTED_PATHS` from the walk. Tests:

1. `test_tree_has_expected_paths`: 56 paths, and the walk contains `("config", "providers", "create")` and `("channels", "telegram", "configure")`. This catches a broken walk.
2. `test_every_parser_has_one_doc_action`: each parser has exactly one `DocAction` registered for `--doc`, and its `guide_path` equals the walk path.
3. `test_every_path_has_guide` + `test_no_orphan_guides`: the set of `guides/*.md` names equals `{guide_filename(p) for p in EXPECTED_PATHS}`.
4. `test_guard_flags_new_subparser_without_guide` (AC2 negative): build a parser, add a fake `zz-undocumented` subparser to the root subparsers action, run `attach_doc_options` on it, and assert that the test's `_paths_without_guides()` helper returns `[("zz-undocumented",)]`. Also assert that `parse_args(["zz-undocumented", "--doc"])` exits 1 with the "no --doc guide" message on stderr.
5. `test_doc_prints_guide_and_exits_zero[path]` (parametrized over all 56): `cli.main([*path, "--doc"])` raises `SystemExit(0)`; stdout equals the guide text, is non-empty, and starts with `# pbi-agent`; stderr is empty. `main` is patched so that `run_startup_maintenance` raises `AssertionError` (this also proves the exit happens before maintenance).
6. `test_guide_has_required_sections[path]`: leaves need Purpose, Usage, Options and arguments, Examples, Workflows, Related commands, Pitfalls. Parents need those plus Subcommands. Root needs Overview, Usage, Global options, Settings resolution, Commands, Examples, Getting more detail, Pitfalls. The H1 must equal `# pbi-agent <path>`. The guide must be ASCII, with no `\x1b`.
7. `test_parent_guide_lists_children[path]`: each canonical child appears as `` `pbi-agent <path> <child>` `` in Subcommands, and the section mentions `--doc`. The root `## Commands` section contains every one of the 55 paths, and `upgrade.md` mentions `pbi-agent update`.
8. `test_guide_documents_every_option[path]`: every visible action (help not `SUPPRESS`, excluding help, `DocAction` and subparsers actions) must appear as a token inside a backtick span in Options and arguments (Global options for the root). Options use their longest option string, positionals use `metavar or dest`. Tokens are split on space, comma and `=`.
9. `test_guide_examples_parse[path]`: every line in ```bash blocks that starts with `pbi-agent` (after optional `VAR=value` prefixes) is `shlex.split` and parsed with `build_parser().parse_args(_argv_with_default_command(...))`. Parsing must not end in `SystemExit(2)`; `SystemExit(0)` from `--help`/`--doc` is allowed, with stdout patched. No line may end with `\`.
10. `test_doc_has_no_side_effects[argv]` for `run --doc`, `web --doc` and `config providers create --doc`, in-process:
    - Setup: `HOME`/`USERPROFILE` point at `tmp_path`; `*_API_KEY` env vars are removed; cwd is set with `monkeypatch.chdir` to an empty dir, so no `.env` can load.
    - These are patched with `side_effect=AssertionError`: `pbi_agent.cli.entrypoint.run_startup_maintenance`, `resolve_runtime`, `resolve_web_runtime`, `configure_logging`, `_handle_run_command`, `_handle_web_command`, `_handle_config_command`, `pbi_agent.config.load_dotenv`, `urllib.request.urlopen`, `socket.create_connection`.
    - Asserts: `SystemExit(0)`, and the `rglob` snapshot of `tmp_path` and the cwd is unchanged. The conftest config, session DB and other paths live under `tmp_path`, so no config write can go unseen.
11. `test_doc_subprocess_matches_help_side_effects[argv]` for the same three paths:
    - Run `[sys.executable, "-m", "pbi_agent", *argv]` with `env` = `os.environ` minus `PBI_AGENT_*` and `*_API_KEY`, plus `PYTHONPATH=<repo>/src`, `HOME`/`USERPROFILE` set to a fresh dir, cwd an empty dir, and `timeout=60`.
    - Asserts: rc 0; stdout starts with `# pbi-agent`; stderr is empty; no `.pbi-agent/config.json`; the cwd stays empty; and the set of files created under HOME equals the set created by the same path with `--help` in another fresh HOME (accepted parity: `.pbi-agent/sessions.db`).
12. `test_help_mentions_doc[path]`: with the terminal size patched to 120, each parser's `format_help()` contains `[--doc]` and the `--doc` row text. The root help also contains `pbi-agent --doc`.
13. `test_argv_with_default_command_keeps_root_doc`: `["--doc"]` stays `["--doc"]` and `["--verbose", "--doc"]` stays `["--verbose", "--doc"]`. `cli.main(["--doc"])` prints the root guide, not the web guide.

All existing `tests/cli/*` stay unmodified and must pass (AC7).

## Acceptance criteria map
| AC | Proven by |
| --- | --- |
| 1 `--doc` everywhere, non-empty, exit 0 | tests 1, 5, 13; smoke commands below |
| 2 no command without a guide | tests 2, 3, 4 |
| 3 `run`/`web`/`config providers create` with no args, no config, no side effects | tests 10, 11 (+ test 5 maintenance guard); import-time `sessions.db` accepted as `--help` parity (human decision at triage) |
| 4 guide content | tests 6, 7, 8, 9; reviewer reads a sample (root, `run`, `config providers create`, `channels telegram`) against code |
| 5 `--help` mentions `--doc` | test 12 |
| 6 docs | `docs/cli.md` section; `bun run docs:build` |
| 7 behavior/help unchanged apart from `--doc` | existing `tests/cli` unchanged and green; the before/after help dump diff recorded in `build.md` shows only the accepted `--doc` lines |
| profile `acceptance_tests` | this table, with results recorded in `build.md` |
| profile `docs` | `docs/cli.md` change + `bun run docs:build` |

## Validation (build)
1. Before any edit, dump the baseline help to scratch: a scratchpad script walks `build_parser()` with `shutil.get_terminal_size` patched to 120 and writes every path's `format_help()` to `<scratch>/help-before.txt`. Repeat after the change into `help-after.txt`, then run `diff <scratch>/help-before.txt <scratch>/help-after.txt`. Every hunk must be a `[--doc]` token, a re-wrap, the `--doc` row or the root epilog. Record a summary in `build.md`.
2. `uv run pytest -q --tb=short -x tests/cli/test_doc.py`
3. `uv run pytest -q --tb=short -x tests/cli`
4. `uv run pytest -q --tb=short -x`
5. `uv run ruff check .` / `uv run ruff format --check .` / `uv run basedpyright`
6. `bun run docs:build`
7. Packaging: run `uv build --out-dir <scratch>/dist`, then check with python3 `zipfile`/`tarfile` that the wheel has 56 `pbi_agent/cli/guides/*.md` and the sdist has 56 `src/pbi_agent/cli/guides/*.md`.
8. Smoke tests in a fresh HOME and an empty cwd (`H=$(mktemp -d)`), using `HOME=$H uv run --project <repo> pbi-agent ...`:
   - `--doc | head -5`, `run --doc`, `web --doc`, `config providers create --doc`, `update --doc` (all rc 0, Markdown);
   - `--help | grep -- --doc`;
   - `run --help | grep -- --doc`;
   - `find $H -type f` shows only `.pbi-agent/sessions.db`.

No frontend checks are needed, because `webapp/` is not touched.

## Assumptions and defaults
- Guides ship as package `.md` files rather than a Python module. This keeps reviewable Markdown, follows the `importlib.resources` precedent in `models/messages.py:28`, and needs no `pyproject.toml` change (verified for wheel and sdist).
- The import-time `sessions.db` creation is accepted (human decision). The subprocess test enforces parity with `--help`, so it does not enforce zero writes.
- Command-level `--help` mentions `--doc` through the usage token and the options row only. Only the root epilog changes.
- Hidden root API-key aliases and hidden `web --no-open` get no required guide entry. The root guide mentions the aliases briefly.
- Out of scope: `docs/cli.md` coverage gaps (sessions, hooks, channels, maintenance), the changelog (written at release), and `allow_abbrev` changes.
- Risk stays high (about 60 files and about 3,500 lines, almost all guide content). No provider, shell, session-store, web-API or packaging files change.
