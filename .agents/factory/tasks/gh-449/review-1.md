# Review: gh-449, round 1

review: findings: 1

Scope: `src/pbi_agent/cli/doc.py`, `src/pbi_agent/cli/parser.py`, `src/pbi_agent/cli/guides/*.md` (56), `tests/cli/test_doc.py`, `docs/cli.md`. Out of scope and not reviewed: `.agents/**`, `MEMORY.md`, `TODO.md`.

## Verification performed
- `uv run pytest -q --tb=short -x tests/cli`: pass.
- AC7 help parity, checked independently and not from the worker's scratch files: I built a baseline from `git show HEAD:src/pbi_agent/cli/parser.py` in a scratch copy of `src/` and dumped all 56 `format_help()` outputs at width 120, before and after. After removing `[--doc]`, the `--doc` row and the new epilog sentence and normalizing whitespace, 0 of 56 sections differ. The root usage line is a custom string, so it stays unchanged.
- AC3 precedence: `DocAction` (`nargs=0`, `SUPPRESS` dest) exits inside `parse_args`. That is before `run_startup_maintenance`, `--mcp`/`--agents`, the web runtime-flag rejection, `load_dotenv` (called only inside `resolve_runtime`/`resolve_web_runtime`), config resolution and the handlers (`entrypoint.main`). The `"--doc"` entry in `_default_command_insertion_index` makes `pbi-agent [globals] --doc` print the root guide and not insert `web`. Even without that entry the root action would fire first.
- AC2 guard: `test_every_path_has_guide` walks the real `build_parser()` tree with its own walker, so a new subparser without a guide fails it. `test_guard_flags_new_subparser_without_guide` proves the negative case: the walker flags it, and its `--doc` exits 1 with the message.
- Packaging: the scratch wheel has 56 `pbi_agent/cli/guides/*.md` plus `cli/doc.py`. `requires-python >=3.12` covers multi-arg `Traversable.joinpath`.
- Guide content checked against the code: root, `run`, `web`, `sandbox`, `config providers create`, `config providers auth-login`, `config profiles create`, `config maintenance set`, `kanban create`, `channels telegram configure`, `hooks`, `hooks trust`, `upgrade`, `sessions`, `init`, `skills enable`, `kits add` (spot checks).
  - What I confirmed: flags and defaults, the env var names, the resolution order (`resolve_runtime`, `_resolve_secret`), the `medium` reasoning default, provider kinds and auth modes (`provider_auth_modes`), the slug rules, the error strings and exit codes, the web port fallback, the dev CORS ports, the 65535 check, the instance lease message, and the sandbox docker flags, mounts and forwarded env vars.
  - Further details I confirmed: the Alpine/`USER pbi` image, the auth callback ports 1455 and 56121, the 5 and 15 minute flow timeouts, the `auth.json` path, the hooks events, the `hooks_state.json` path, the 600s timeout, the telegram payload merge semantics, the kanban stage matching and JSON keys, and the upgrade installers and PyPI timeout.
  - Result: apart from the item below, I found no invented or wrong flags, defaults or behaviors.
- The four extra `docs/cli.md` corrections are all correct against the code:
  - the bare `pbi-agent --api-key` invocation is rejected through the implicit `web` (`entrypoint.main` plus `_web_runtime_flags_in_args`);
  - `_default_reasoning_effort` returns `medium`;
  - `AUTH_MODE_XAI_ACCOUNT` is in both `--auth-mode` choice lists;
  - `media.py` gives PNG/JPEG/WEBP/HEIC/HEIF by content sniffing with `_MAX_IMAGE_BYTES` 20 MB.
- Out-of-scope note: `docs/environment.md:20` still says `xhigh`/`high` for `PBI_AGENT_REASONING_EFFORT`, which now contradicts `docs/cli.md`. The plan scoped it out, and `build.md` records it.

### Findings

#### [P3] Correct the claim that `web` never writes saved config
- title: Correct the claim that `web` never writes saved config
- priority: 3
- confidence_score: 0.8
- absolute_file_path: /home/drod/workspace/pbi-agent/src/pbi_agent/cli/guides/pbi-agent.md
- line_range: 75-75
- The root guide says "Only `pbi-agent config ...` commands write saved configuration; `run` and `web` never rewrite it." `config.md:10` says the same: "`run` and `web` read this file but never rewrite it". The web UI served by `pbi-agent web` does write `~/.pbi-agent/config.json`. Its Settings backend calls `create_provider_config`, `create_model_profile_config`, `select_active_model_profile` and `update_maintenance_config` (`src/pbi_agent/web/session/configuration.py:47-72,159,218,530`). The same root paragraph tells the user to select the profile "in the web Settings", and `config.maintenance.set.md` says web Settings "edits the same value", so the guides contradict each other. An agent that trusts this sentence could expect config to stay unchanged while a web server is running, and miss revision conflicts. Suggested wording: only `pbi-agent config ...` and the web UI Settings page write saved configuration, and `run` and starting `web` only read it.

### Overall Correctness
- overall_correctness: patch is correct
- overall_explanation: The `--doc` mechanism is sound. It exits during parsing with no side effects, the guard really catches a missing guide, and `--help` output is byte-equivalent apart from the accepted `--doc` additions. The guides match the code closely. The only issue is one inaccurate sentence in the documentation (repeated in two guides), which does not block.
- overall_confidence_score: 0.85
