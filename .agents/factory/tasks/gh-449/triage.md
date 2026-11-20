# Triage: gh-449 (add `--doc` to every pbi-agent CLI level)

## Summary
The CLI is a single argparse tree built in `src/pbi_agent/cli/parser.py` (plus `channels.py`), with 56 distinct parsers: the root and 55 command/subcommand paths, up to depth 3, plus one alias (`update` for `upgrade`). Nothing like `--doc` exists today. All side-effecting work (maintenance, config resolution, server start) runs after `parse_args`, so a `--doc` built as an argparse Action that exits, the way `-h` and `-v` do, meets the "no required args / no side effects" requirement. One side effect already happens at import time for `--help` too: importing `pbi_agent.cli` creates `~/.pbi-agent/sessions.db`. The guide content (about 56 guides) will put the diff well over the 500-line and 15-file thresholds, so risk becomes high.

## Findings

### Parser construction and dispatch
- `src/pbi_agent/__main__.py:1-4` calls `pbi_agent.cli.main`. `src/pbi_agent/cli/__init__.py:3-13` re-exports `main` from `entrypoint` and `build_parser`, `CleanHelpFormatter`, `ExplicitPortAction` and `_argv_with_default_command` from `parser`.
- `src/pbi_agent/cli/parser.py:56-67` builds the root parser: `prog="pbi-agent"`, custom `usage`, `description="Lightweight local coding agent."`, `epilog` (lines 61-64: "Run `pbi-agent <command> --help` for command-specific options. Defaults to `web` when no command is provided."), `formatter_class=CleanHelpFormatter`, `allow_abbrev=False`. This epilog is the natural place for the root `--help` mention of `--doc`.
- `src/pbi_agent/cli/parser.py:68-246`: root global options are in argument groups ("Provider and API", "Model behavior", "Runtime and resilience", "Diagnostics"). Six hidden API-key aliases use `help=argparse.SUPPRESS` (lines 108-137).
- `src/pbi_agent/cli/parser.py:248-265`: root subparsers use `dest="command"` and `required=False`. The helper `add_command_parser(name, help_text, aliases=...)` sets `prog=f"pbi-agent {name}"`, `description=help_text`, `help=help_text` and `formatter_class=CleanHelpFormatter`. Top-level commands go through it. Deeper subparsers call `add_parser(...)` directly with an explicit `prog`/`description`/`formatter_class` (for example lines 420-460, 532-538, 555-605, 635-830, 867-1199).
- `src/pbi_agent/cli/channels.py:23-148`: `add_channels_parser(add_command_parser, formatter_class=...)` builds the `channels` subtree outside `parser.py`. It is called at `parser.py:622-625`. A design that only patches `add_command_parser` or `parser.py` call sites would miss this subtree. The safest option is a post-build walk of the finished tree.
- `src/pbi_agent/cli/parser.py:1203` `return parser`: one exit point. A post-build pass over all parsers can add `--doc` there (after all other args).
- Dispatch is `src/pbi_agent/cli/entrypoint.py:47-176`. `main()` builds the parser (48), parses `_argv_with_default_command(parser, raw_argv)` (50), and only then runs `run_startup_maintenance(...)` (52-55), which opens the SessionStore, purges old data and checks PyPI for updates (`src/pbi_agent/maintenance.py:34-58`). Per-command routing follows (59-175). `configure_logging` (111, 129, 163), `resolve_web_runtime` (131), `resolve_runtime` → `load_dotenv` (161; `src/pbi_agent/config.py:962,990,1497,1747`) and the web server start (154) all run after parsing.
  - So an Action that prints and calls `parser.exit(0)` during `parse_args` (the pattern `_HelpAction`/`_VersionAction` use) skips maintenance, the update check, `.env` loading, config and server start. **A `store_true` flag checked after `parse_args` would fail AC3**: required-arg errors would fire (e.g. `run -p`), and maintenance plus the network update check would run.
- Default `web` insertion is in `src/pbi_agent/cli/parser.py:1206-1255` (`_argv_with_default_command` / `_default_command_insertion_index`). Line 1229 returns `None` (no insertion) only for subcommand names and `{"-h","--help","-v","--version"}`. Today `pbi-agent --doc` becomes `web --doc` (unknown option → index 0). Once `--doc` is a root option with `nargs=0`, the walk skips it and appends `web` (`["--doc","web"]`). The root action then fires first and prints the root guide, but the cleaner fix is to add `--doc` to the set at line 1229, mirroring `--help`. Tests for this pattern are at `tests/cli/test_parser.py:43-60`.
- `src/pbi_agent/cli/parser.py:1258-1262` `_subcommand_names` already walks `_SubParsersAction`. The same private-API pattern is used across tests (e.g. `tests/cli/test_parser.py:101-107`).

### Pre-existing import-time side effect (confirmed)
- Importing `pbi_agent.cli` creates `~/.pbi-agent/sessions.db` before any parsing. Chain: `cli/__init__.py:3` → `entrypoint.py:29` → `cli/channels.py:10` → `channels/setup.py:5` → `channels/manager.py:6` → `channels/telegram.py:16` → `agent/session/__init__.py:6` → ... → `agent/system_prompt.py:21` → `tools/registry.py:29` → `tools/sub_agent.py:124` (`SPEC = build_spec()` at module level) → `agents/state.py:63` (`with SessionStore() as store`) → `session_store.py:924` (`sqlite3.connect`).
- The same thing happens for `pbi-agent run --help` today (shown under Reproduction). It is not a config write (`config.json` is untouched), no network is used, and it matches `--help` parity. Removing it would mean touching `tools/sub_agent.py`/`session_store.py`, which is a high-risk area and out of scope. See Unknowns.

### Command tree (programmatic walk)
Walked with a script that recurses through `argparse._SubParsersAction.choices` and dedups aliases by parser identity (`uv run python3 <scratch>/walk.py`). There are 56 parsers: the root plus 55 paths. `update` is the only alias and is also the only choice missing from `_choices_actions`, because argparse lists it as `upgrade (update)`. There are no other hidden subcommands.

| depth | path | required / positional | hidden options | subparsers |
| --- | --- | --- | --- | --- |
| 0 | (root) | – | --openai/--azure/--xai/--google/--anthropic/--generic-api-key | dest=command, required=False (default `web`) |
| 1 | run | -p/--prompt | | |
| 1 | init | | | |
| 1 | upgrade (alias `update`) | | | |
| 1 | web | | --no-open | |
| 1 | sandbox | | | dest=sandbox_command, required=False (default `web`) |
| 2 | sandbox web | | | |
| 2 | sandbox run | -p/--prompt | | |
| 1 | sessions | | | |
| 1 | hooks | | | dest=hooks_action, required=False |
| 2 | hooks trust / enable / disable | hook_key (pos) | | |
| 1 | kanban | | | required=True |
| 2 | kanban create | --title, --desc/--description/--prompt | | |
| 2 | kanban list | | | |
| 1 | channels | | | required=True |
| 2 | channels show | | | |
| 2 | channels telegram | | | required=True |
| 3 | channels telegram show / configure / restart | | | |
| 1 | skills | | | required=True |
| 2 | skills list | | | |
| 2 | skills enable / disable | skill (pos) | | |
| 2 | skills add | source (pos) | | |
| 1 | commands | | | required=True |
| 2 | commands list / add (source pos) | | | |
| 1 | agents | | | required=True |
| 2 | agents list / add (source pos) | | | |
| 1 | kits | | | required=True |
| 2 | kits add | source (pos) | | |
| 1 | config | | | dest=config_scope, required=True |
| 2 | config maintenance | | | dest=config_action, required=True |
| 3 | config maintenance show | | | |
| 3 | config maintenance set | --retention-days | | |
| 2 | config providers | | | required=True |
| 3 | config providers list | | | |
| 3 | config providers create | --name, --kind | | |
| 3 | config providers update / delete / auth-status / auth-login / auth-refresh / auth-logout / usage-limits | provider_id (pos) | | |
| 3 | config providers auth-import | provider_id (pos), --access-token | | |
| 2 | config profiles | | | required=True |
| 3 | config profiles list | | | |
| 3 | config profiles create | --name, --provider-id | | |
| 3 | config profiles update / delete / select | profile_id (pos) | | |

- `-h` already works under required subparsers and required args: `kanban --help`, `config providers create --help` and `run --help` all exit 0. An exiting `--doc` Action behaves the same way.
- `update` shares the `upgrade` parser object (prog `pbi-agent upgrade`), so an alias automatically shows its target's guide. This matches the issue's open assumption.

### Help formatting and help tests
- `src/pbi_agent/cli/parser.py:42-53` `CleanHelpFormatter` sets width 100-120 from the terminal size and a help position of at most 42. Every parser uses it. Only the root has an epilog. Command parsers have only `description=help_text`.
- Existing custom Actions: `ExplicitPortAction` at `parser.py:29-39` (sets a sentinel on the namespace), and the built-in `action="version"` at `parser.py:68-74`. There is no epilog/doc mechanism beyond the root epilog.
- The help tests check substrings, not snapshots:
  - `tests/cli/test_parser.py:109` asserts `"usage: pbi-agent web [-h] [--host HOST] [--port PORT]"`. **If `--doc` is added before the other options, the usage becomes `[-h] [--doc] [--host ...]` and this test breaks.** Adding `--doc` after all other arguments (post-build) keeps it.
  - `tests/cli/test_parser.py:80-98` checks the alignment of root help rows. Adding a short `--doc` option does not affect it.
  - `tests/cli/test_parser.py:124-128` asserts that root help omits `" console "`/`" open "`. The `--doc` help text must not contain those words.
  - `tests/cli/test_kanban.py:46-51,66-70` and `tests/cli/test_channels.py:56-67` assert `usage: pbi-agent kanban create`, option strings, and so on. These are prefix substrings, so they are safe.
  - `tests/cli/test___init__.py:6-9` checks facade exports only.
- Abbreviation edge case (inference, not tested): subparsers keep argparse's default `allow_abbrev=True` (only the root sets `False`, at `parser.py:66`). Today `pbi-agent web --d` resolves to `--dev`. After `--doc` is added it becomes ambiguous. The same applies to `sandbox --d` (`--detach`), `sandbox web --d`, and `channels telegram configure --d` (`--disable`). This is a minor behavior change in an undocumented shorthand. The planner should note it and probably accept it.

### Docs site
- `docs/cli.md:1-4` has frontmatter `title`/`description`. `docs/cli.md:8` says "`-h` and `--help` are available at the root and on every subcommand", which is the natural place to document `--doc`. Sections: Global Options (14), Hidden API-Key Aliases (53), skills (65), commands (98), agents (146), kits (195), init (223), upgrade (234), kanban (265), config (310; providers 320, profiles 346), web (362), sandbox (386), run (421), Image Input Support (447).
- `docs/cli.md` has **no section** for `sessions`, `hooks`, `channels` (incl. `telegram`), `config maintenance`, `skills enable/disable` or `config providers usage-limits` (grep counts 0 for hooks/channels/telegram/maintenance/usage-limits/"skills enable"). Guides for those must be written from code (handlers in `src/pbi_agent/cli/{sessions,hooks,channels,config,catalogs}.py`) and other pages (`docs/customization/hooks.md`, `docs/sandbox.md`, `docs/kanban-dashboard.md`, `docs/model-profiles.md`, `docs/providers.md`, `docs/environment.md`). Guides can partly derive from `docs/cli.md` for the covered commands, but must be authored separately. Single-sourcing is out of scope.
- `docs/.vitepress/config.ts:115` already links `/cli`. No nav change is needed.

### Packaging (for guide storage)
- `pyproject.toml:25-31`: hatchling includes git-tracked non-Python files inside packages automatically, so per-path `.md` guides under e.g. `src/pbi_agent/cli/<dir>/` ship without a `pyproject.toml` edit (that edit would be a risk trigger). The precedent for reading package data is `importlib.resources.files("pbi_agent.models")` at `src/pbi_agent/models/messages.py:28`.

### AC 2 enumerability
- Confirmed: a test can enumerate every path by recursing through `_SubParsersAction.choices` from `build_parser()` and deduping by `id(parser)` for aliases (the walk script above does exactly this, and the repo already uses this private API at `parser.py:1258-1262` and in tests). The test can then assert that each path has a non-empty guide containing the required sections. It can also run `build_parser().parse_args([*path, "--doc"])` (or `cli.main`) and expect `SystemExit(0)` with Markdown on stdout, and check in reverse that no guide is orphaned. A new subparser without a guide then fails the test.

### Not already done
- `grep -- "--doc"` over `src/pbi_agent/cli`, `tests/cli` and `docs/cli.md` finds nothing. `pbi-agent --doc` currently fails with `error: unrecognized arguments: --doc`. No branch or commit addresses #449 (recent log ends at `a9616814 add factory`).

## Reproduction
Not a bug. Current state and side-effect baseline:

```
$ HOME=<fresh tmp> uv run --no-sync pbi-agent run --help >/dev/null; echo rc=$?
rc=0
$ HOME=<fresh tmp> uv run --no-sync pbi-agent config providers create --help >/dev/null; echo rc=$?
rc=0
$ find <fresh tmp> -name sessions.db
<fresh tmp>/.pbi-agent/sessions.db        # created at import time, even for --help
$ HOME=<fresh tmp> uv run --no-sync pbi-agent --doc
usage: pbi-agent [GLOBAL OPTIONS] [<command>] [COMMAND OPTIONS]
pbi-agent: error: unrecognized arguments: --doc
```

Importing `pbi_agent.config` alone creates nothing. Importing `pbi_agent.cli` (or `pbi_agent.cli.parser`) creates `.pbi-agent/sessions.db`, traced to `tools/sub_agent.py:124`.

## Unknowns
- Is the pre-existing import-time `~/.pbi-agent/sessions.db` creation (shared with `--help`) acceptable under AC3's "no side effects"? Recommendation: accept `--help` parity, record it in `build.md`, and keep the fix out of scope (it would touch `tools/sub_agent.py` and `session_store.py`). The human can confirm at the plan gate. If strict zero-write is wanted, that is a separate high-risk task. (needs human only if they reject parity)
- Guide storage format (one `.md` per path loaded through `importlib.resources`, or a Python mapping) and the key scheme (path tuple → file name). This is the planner's decision.
- Exact `--doc` help text and placement. Recommend adding it after all other args in a post-build walk, so existing usage substrings (`tests/cli/test_parser.py:109`) stay valid, plus one root epilog sentence. This is the planner's decision.
- How deep the leaf guides need to go (e.g. `config providers auth-refresh`) while still covering all six required sections without padding. This is the planner's or reviewer's call.
- Accepting the abbreviation ambiguity (`web --d`, `sandbox --d`, `channels telegram configure --d`). Planner: note it as a known pitfall.
- `bun run docs:build` baseline was not run during triage.

## Scope estimate
- Surfaces: python (CLI and tests), docs (`docs/cli.md`), plus packaged Markdown guide content.
- Likely files or areas: `src/pbi_agent/cli/parser.py` (DocAction, post-build attach, epilog mention, `parser.py:1229` default-insertion set), possibly a new `src/pbi_agent/cli/docs.py` and a guide directory (about 56 guides), `tests/cli/test_parser.py` or a new `tests/cli/test_doc.py`, `docs/cli.md`. `entrypoint.py` should need no change if the Action exits during parsing.
- Size estimate: code about 80-150 lines, tests about 80-150 lines, guide content about 2,500-4,500 lines (56 guides at roughly 40-80 lines each), and `docs/cli.md` about 20-40 lines. If guides are separate files, expect about 60 or more files.

## Risk and profile
- risk: high. Triggers: the diff will exceed both 500 changed lines and 15 files, mainly guide content. One unknown (the import-time DB creation under AC3) needs human confirmation of `--help` parity. No provider, shell, session-store, web-API, packaging (`pyproject.toml`) or workflow paths need changing if guides ship as git-tracked package data.
- profile: keep `build`. It adds a new user-visible CLI flag, and build is already the strictest profile.

## Verdict
triage: proceed. The work is not yet done, and the tree can be enumerated in a test. An exiting argparse Action keeps `--doc` free of side effects apart from the existing import-time `sessions.db` creation it shares with `--help`. The large size makes the task high-risk, but nothing here blocks it.
