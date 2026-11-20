# Retrospective Report: gh-449 (`--doc` guides for every CLI path)

## Outcome
Validated win. PR #451 merged as `2e68f9a6` with CI green (Tests, Deploy Docs). Issue #449 is closed. `verify.md` confirms all 7 acceptance criteria on merged `master`. Every human gate was `approved_unchanged`.

The process did not close on its own, though. The conductor had to fill four gaps by hand: the unpushed local commit, the docs contradiction, the flaky full suite and TODO.md handling. The next rep should not need those fixes.

## Evidence from Trace
Sources: the task folder files, conductor notes, and two spot checks run for this report. The session DB was not queried, because the run used a Claude Code conductor and not the pbi-agent runtime, so the DB has no trace of it. That part of the trace is missing.

- **Gate log (`task.md`).**
  - triage, plan, review and release: `approved_unchanged`.
  - intake, build and verify: `auto_pass`.
  - Risk rose from normal to high at triage. The triggers were the diff size (about 60 files and 3.9k lines, almost all guide Markdown) and the `sessions.db` unknown.
- **Review loops.**
  - reviewer: 2 rounds. Round 1 had one P3 (a guide claimed `web` never writes config). Round 2 was clean.
  - code-quality-reviewer: 2 rounds. Round 1 had one major finding: the guide-to-parser sync guard only checked one direction (`quality-1.md`). Round 2 was clean.
  - No stage went back, and no rerun limit was reached.
- **Docs contradiction (`build.md`, `review-1.md`).**
  - The worker fixed 4 wrong `docs/cli.md` lines, which the plan allowed ("fix that `docs/cli.md` line minimally"). The reviewer confirmed all 4.
  - One of them, the `--reasoning-effort` default `medium`, left `docs/environment.md:20` still saying `xhigh`/`high`.
  - The worker noticed this and wrote it down as out of scope. The conductor added it to `fix-1`.
- **Missing reverse guard (`quality-1.md`, `fix-2.md`).**
  - The plan's test plan (tests 8-9) only checked parser-to-guide.
  - The reverse check found real drift right away: `channels telegram` named `--token-env-var` and `--token-secret`, which exist only on `configure`.
- **Nested delegation (`build.md`).** The worker had six nested sub-agents write the guides. The plan allowed this ("If the worker delegates guides to sub-agents ..."). In the pbi-agent runtime, `src/pbi_agent/tools/sub_agent.py:217-233` rejects nested runs unless the agent's frontmatter declares a scoped `sub_agents` list, and `worker.md` declares none. Nested time would also count against the parent's 1800 s cap. So this build cannot be reproduced as written under `pbi-agent`.
- **Flaky test at release (`task.md` gate log).**
  - `tests/test_web_serve.py::test_lost_manager_lease_rejects_new_live_sessions` failed 2/15 on clean HEAD and 3/15 with the change.
  - It failed in 1 of 4 full release runs.
  - `.agents/memory/2026-11-12.md:23` already records it ("fails on clean tree"), but nothing in `MEMORY.md` or `AGENTS.md` mentions it, so the conductor found it again by repeated runs.
- **No pytest summary.**
  - `pyproject.toml:52` has `addopts = "-q --tb=short -x"`. Every `AGENTS.md` pytest command adds another `-q`, which makes `-qq`, and `-qq` drops the summary line.
  - Checked here: `uv run pytest -q tests/cli/test___init__.py` prints only `.  [100%]`. Plain `uv run pytest tests/cli/test___init__.py` prints `1 passed in 0.21s`.
  - The worker had to use `-o addopts=""` to read totals (`build.md` Assumptions).
- **Unpushed local commit.** Intake found local `master` 1 commit ahead (`a9616814 add factory`). `factory.md` has no rule for this. `commit.md` step 1 branches from `master`, so the PR would have carried that commit without anyone deciding to ship it. The conductor raised it as a PR-scope question at the release gate. The human chose to ship it as separate commits in PR #451.
- **Human corrections mid-run.**
  - (a) Task folders are committed, not gitignored. This was already applied to `operator.md` and `factory.md` during the run.
  - (b) TODO.md: the conductor overwrote it, then restored it and appended to it. The human then asked to keep only this session's items. Read literally, the `AGENTS.md` rule "session-only; reset if complete, append if unfinished" allowed all three.
- **Gate log shape.** The gate log mixes gate decisions with reviewer rounds (`findings: 1`, `fix: done`), validation evidence (`pass`) and a release row whose decision is `shipped`. The ledger is "one row per gate decision", and promotion counts consecutive `approved_unchanged` rows. Both depend on clean decision rows.

## Where the Workflow Broke Down
1. **Release validation was nondeterministic.** A known flake plus `-x` made the full suite fail about 1 run in 7. With no recorded policy, the conductor spent 15+15 isolated runs and 4 full runs proving the failure was unrelated. This was the largest avoidable cost in wall-clock time.
2. **Scope decisions came late.** The ahead-of-origin commit was found at intake but decided only at release. It was resolved by improvising, not by a rule.
3. **The plan was narrower than the facts.** The plan limited doc fixes to one page, so a correct fix created a contradiction across pages. Its drift test only checked one direction, which cost one fix round in each review loop (fix-1 in part, fix-2 fully).
4. **The run depended on the host.** Nested delegation in the build and the untested `worker`/`fixer` `model_profile_id: worker` profile mean this run does not show that `/factory` works under the pbi-agent runtime.
5. **Convention ambiguity needed a human.** TODO.md handling needed a human correction, and the task-folder commit policy needed another.

## Customization Diagnosis
| Issue | Layer | Why this layer |
| --- | --- | --- |
| Flaky test and the missing pytest summary | `AGENTS.md` | These are repo-wide testing facts. Every session that runs the suite needs them, not only factory runs. |
| A new CLI command needs a guide | `AGENTS.md` | A new repo convention enforced by tests. Every session adding a subcommand or flag hits it. |
| TODO.md reset semantics | `AGENTS.md` | `factory.md` defers to the `AGENTS.md` TODO rule, so the ambiguity lives there. |
| Unpushed local commits | command (`factory.md`) | The decision belongs to the conductor's intake and release gate. `commit.md` follows the scope the conductor passes. |
| Gate log vs ledger hygiene | command (`factory.md`) | It defines the gate log, the ledger and promotion. |
| Nested delegation in build | command (`factory.md`) | The conductor owns how stages run. Fixing it in the plan alone would still let a worker try nested runs. |
| Missing reverse drift guard | command (`plan.md`) | A planning-stage rule: what the test plan must contain. The reviewer caught it, but only after a build. |
| Same fact left wrong on another page | agent (`worker.md`) | Execution-time habit. It applies to any doc correction a worker makes, whatever the plan wording. |

## Recommended Changes

### 1. Testing facts: flaky test and pytest output
- **Target layer:** `AGENTS.md` (Testing Conventions and Common Commands)
- **Change:**
  - Record the known flake and how to handle it.
  - Remove the duplicate `-q --tb=short -x` from the pytest commands, because `addopts` already sets them.
- **Why:**
  - The release took 4 full runs plus 30 isolated runs.
  - The 2026-11-12 note already knew about the flake, but no preloaded file mentions it.
  - `-q` on top of `addopts` gives `-qq`, which has no summary (checked here).
- **Expected effect on next rep:** Release validation becomes deterministic. Agents can read the pass/fail totals again, which helps reliability and speed.

### 2. A CLI change needs a `--doc` guide
- **Target layer:** `AGENTS.md` (Architecture Snapshot)
- **Change:** Any new command, subcommand or visible option needs `src/pbi_agent/cli/guides/<dotted.path>.md`. `tests/cli/test_doc.py` enforces this in both directions: missing guides, stale flags and usage drift.
- **Why:** gh-449 added 56 hand-written guides with forward and reverse guards. The next CLI change fails `tests/cli` unless the agent knows this.
- **Expected effect on next rep:** No surprise test failures, and guides stay in sync with the parser. This helps the setup adapt as the codebase changes.

### 3. TODO.md is per session
- **Target layer:** `AGENTS.md` (TODO)
- **Change:** Replace "reset if complete, append if unfinished" with an explicit rule (see the draft below).
- **Why:**
  - The conductor tried overwriting, then restoring and appending.
  - The human then corrected it to keep only this session's items.
  - The current wording allows all three readings.
- **Expected effect on next rep:** No human correction needed. Needs human confirmation that this is a lasting preference.

### 4. Decide unpushed local commits at intake
- **Target layer:** command (`.agents/commands/factory.md`, Intake and Release stage notes)
- **Change:**
  - At intake, list the commits ahead of `origin/<base>` in `task.md`.
  - If there are any, the release-gate question must offer the scope options.
  - Pass the chosen scope to `operator` explicitly.
  - Never let release branch from an ahead `master` without that decision.
- **Why:** There was no rule, and `commit.md` would have shipped `a9616814` inside the PR silently. The conductor improvised the question.
- **Expected effect on next rep:** Unshipped work is never included by accident, and the gate question is predictable.

### 5. Separate gate decisions from stage evidence
- **Target layer:** command (`.agents/commands/factory.md`, Task folder and Learn)
- **Change:**
  - The gate log holds only gate decisions, from a closed set of values.
  - Reviewer rounds and validation go in a separate `## Stage log`.
  - Ledger rows come only from the gate log.
- **Why:**
  - This run's gate log has rows with decisions `findings: 1`, `fix: done`, `pass` and `shipped`.
  - Promotion counts consecutive `approved_unchanged` rows, so mixed rows would break or skew the count.
- **Expected effect on next rep:** The ledger and the promotion rule stay correct as runs add up.

### 6. No nested sub-agents in build
- **Target layer:** command (`.agents/commands/factory.md`, Build stage note)
- **Change:**
  - Stage agents must not spawn sub-agents.
  - When `plan.md` splits authored content into groups, the conductor runs `worker` once per group, in order, writing `build-<group>.md`, then runs one final `worker` pass for integration and checks.
- **Why:**
  - The gh-449 worker used six nested sub-agents.
  - The pbi-agent runtime rejects that (`sub_agent.py:217-233`, no scoped `sub_agents` in `worker.md`).
  - Nested time would also count against the 1800 s cap that `factory.md` itself cites as the reason for being flat.
- **Expected effect on next rep:** The same plan runs under `pbi-agent` as well as under Claude Code.

### 7. Drift guards in both directions
- **Target layer:** command (`.agents/commands/plan.md`)
- **Change:** When a change adds hand-written content that mirrors code (guides, doc tables, option lists, schemas), the test plan must guard both directions. Code to content: every item is documented. Content to code: nothing documented that the code no longer has.
- **Why:** `quality-1.md` found exactly this gap (major). On its first run, the reverse check found real drift in `channels.telegram.md`.
- **Expected effect on next rep:** One less fix round in the code-quality loop.

### 8. Fix a wrong fact on every page that repeats it
- **Target layer:** agent (`.agents/agents/worker.md`, Handoff discipline)
- **Change:** When correcting a factual claim in docs, grep `docs/` and any packaged docs for the same claim. Either fix every occurrence in the same change, or list each one left in `build.md` under "Contradictions left", so the conductor routes it before review.
- **Why:** The `docs/cli.md` fix of the `medium` default contradicted `docs/environment.md:20`. That needed a reviewer note plus a conductor addition to fix-1.
- **Expected effect on next rep:** A correction no longer creates a contradiction elsewhere, and there is less conductor patching.

## Prompt / Skill / Command Mutations

**`AGENTS.md`, Common Commands.** Replace the pytest lines with:
```bash
uv run pytest                       # addopts already sets -q --tb=short -x
uv run pytest tests/test_cli.py
uv run pytest tests/test_cli.py::DefaultWebCommandTests::test_main_defaults_to_web_for_global_options_only
uv run pytest -m slow
```
Then, in Key Constraints, change every `uv run pytest -q --tb=short -x ...` to `uv run pytest ...`.

**`AGENTS.md`, Testing Conventions.** Add:
```markdown
- `pyproject.toml` `addopts` already sets `-q --tb=short -x`; adding `-q` again yields `-qq` and hides the summary line. Read pass/fail from the exit code, or drop the extra `-q` to see totals.
- Known flaky: `tests/test_web_serve.py::test_lost_manager_lease_rejects_new_live_sessions` (fails about 1 in 7 on clean `master`). If it is the only failure, rerun it once in isolation and rerun the suite once; record both results. Do not treat it as a regression or loop on it. Fixing it is a tracked follow-up.
```

**`AGENTS.md`, Architecture Snapshot.** Add:
```markdown
- CLI `--doc`: every parser path has a packaged guide `src/pbi_agent/cli/guides/<dotted.path>.md` (root: `pbi-agent.md`), attached post-build by `src/pbi_agent/cli/doc.py`. Adding or renaming a command, subcommand or visible option requires updating its guide (and the parent's `## Subcommands` plus the root `## Commands` index); `tests/cli/test_doc.py` fails on missing guides, undocumented options, stale flags and usage drift.
```

**`AGENTS.md`, TODO.** Replace the second bullet with:
```markdown
- `TODO.md` holds only the current session's items. On the first task of a session, clear all previous items (finished or not; durable follow-ups belong in `MEMORY.md` or the task record) and start fresh. Within a session, append and update; never overwrite items added earlier in the same session.
```

**`factory.md`, Intake stage note.** Append:
```markdown
Also run `git rev-list --oneline origin/<base>..<base>`. If the base branch has unpushed commits, list them under `## Environment notes` in `task.md`. They are out of scope unless the human includes them: the release-gate question then adds the options `Ship them as separate commits in this PR`, `Exclude them (release from origin/<base>)`, `Stop`. Pass the chosen scope to `operator` verbatim. Without that decision, release must not start from a base that is ahead of its upstream.
```

**`factory.md`, Task folder.** Replace the `task.md` shape's tail with:
```md
## Gate log
| stage | gate | decision | note |
<!-- decision is one of: auto_pass, skipped, approved_unchanged, approved_with_changes, rejected, blocked -->
## Stage log
| stage | round | result | note |
<!-- reviewer and fixer rounds, validation runs, release outcome -->
```
Then add to the Learn note: "Ledger rows come only from `## Gate log`; one row per gated stage (the combined review+release question logs two rows)."

**`factory.md`, Build stage note.** Append:
```markdown
Stage agents do not spawn sub-agents (the pbi-agent runtime rejects nested runs for agents without a scoped `sub_agents` list, and nested time counts against the parent's cap). When `plan.md` splits the work into groups, run `worker` once per group in plan order, each writing `build-<group>.md` and running that group's checks, then one final `worker` pass that integrates, runs the full checks and writes `build.md`.
```

**`plan.md` command, Test Plan guidance.** Add:
```markdown
If the change adds hand-written content that mirrors code (guides, doc tables, option or schema lists), the test plan must guard both directions: every code item appears in the content, and every item named in the content still exists in the code. Name the test for each direction.
```

**`worker.md`, Handoff discipline.** Add:
```markdown
When you correct a factual claim in docs or packaged guides, grep `docs/` and other packaged docs for the same claim. Fix every occurrence in the same change, or list each one you leave under `Contradictions left` in your handoff with file:line, so it is routed before review.
```

## Next Rep
1. **Intake.** Record unpushed commits and dirty files. Settle commit scope now, or queue the release-gate options.
2. **Triage and plan.** For mirrored content, the plan names both drift tests. Doc corrections are scoped as "fix every occurrence".
3. **Build.**
   - Run one `worker` pass per plan group, then an integration pass.
   - The conductor reruns the checks with `uv run pytest` (summary visible).
   - Under the pbi-agent runtime, first confirm that the `worker`/`fixer` `model_profile_id: worker` profile resolves. That blocker is still open in `MEMORY.md` and was not exercised in this run.
4. **Review.**
   - Run the reviewer loop, then the code-quality loop.
   - Expect fewer rounds now that the plan sets reverse guards and the worker fixes repeated claims across pages.
5. **Release.**
   - Run full validation once.
   - If only the known flaky test fails, rerun it once in isolation and rerun the suite once, then record both and move on.
6. **Verify and learn.**
   - Verify against merged `master`.
   - The ledger takes rows only from the gate log.
7. **Reuse.**
   - The help-dump before/after diff (`dump_help.py` and `check_diff.py` in the scratchpad) worked well to prove AC7. If CLI-help parity comes up again, make it a skill or a test helper.
   - Open product follow-ups from `build.md` are listed in the #449 issue body. Examples: uncaught `config providers` auth tracebacks, and `hooks --project-dir` being overridden by the subparser default. Review-2's incomplete web-Settings writer list is another one.

## Memory candidates
- First live `/factory` run (gh-449, PR #451, 2026-11-20) completed under a Claude Code conductor. All gates were `approved_unchanged`. The pbi-agent-runtime path is still unvalidated: the `worker`/`fixer` `model_profile_id: worker` blocker was not exercised, and the build relied on nested sub-agents, which that runtime rejects. [verified 2026-11-20]
- `uv run pytest -q ...` prints no summary line, because `addopts` already has `-q` and the extra one makes `-qq`. Use the exit code, or drop the extra `-q`. [verified 2026-11-20]
- Known flaky test: `tests/test_web_serve.py::test_lost_manager_lease_rejects_new_live_sessions`. It failed 2/15 on clean HEAD and about 1 in 4 full runs. It predates gh-449 (first noted 2026-11-12). [verified 2026-11-20]
- CLI `--doc` guides live at `src/pbi_agent/cli/guides/<dotted.path>.md`. Every CLI parser or option change needs a guide update, which `tests/cli/test_doc.py` enforces in both directions. [verified 2026-11-20]
- User preference: `TODO.md` keeps only the current session's items, so clear earlier items at session start. [verified 2026-11-20]
- Gate promotion: no profile/stage is eligible yet. Each build-profile gate has 1 `approved_unchanged` row, and 5 are needed.

## Verdict
learn: 8 proposals
