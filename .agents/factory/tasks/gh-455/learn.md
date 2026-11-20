# Retrospective Report

## Outcome
Validated win. PR #456 merged as 79c3a32a with PR checks and CI on the merge commit green. The live Copilot Enhance call returned HTTP 200 with no tool fields on the wire, both at build and again at verify after fix-1. A live Copilot tool turn still sent `tools` and `tool_choice: auto`. All 4 acceptance criteria are confirmed in `verify.md`.

## Evidence from Trace
The task folder is the only trace. The conductor ran in Claude Code (`task.md` Environment notes). `~/.pbi-agent/sessions.db` has no message that mentions gh-455; the only pbi-agent sessions are the verify-skill runs in scratch DB copies.

- Triage reproduced the bug offline (Copilot chat body `{'tools': [], 'tool_choice': 'auto'}`). It also found the root-cause class: commit `79a5a6bb` fixed the shared `ChatCompletionsProtocol`, but `_GitHubCopilotChatCompletionsProvider._http_request` "overrides `_http_request` with its own body ... so the fix never reached it" (`triage.md`, Request builders).
- Plan saw the same fork and still chose to patch the copy: "drop both `tools` and `tool_choice`. ... It matches the generic protocol, which this class's own copy of the body never picked up" (`plan.md`, Key Changes).
- Code-quality r1 then flagged exactly that copy (`quality-1.md`, major: "patches the copy again instead of using the canonical owner"). This cost one fixer round, a validation rerun, code-quality r2, and a full live re-check at verify, because fix-1 changed source after the build live check.
- Build ran `ruff format --check .`, got "1 file would be reformatted" (`triage.md`, because of its Python fence), called it "not owned by this stage, left as is", and still reported `build: checks-pass`. The conductor ran `ruff format` on triage.md (`task.md` Gate log, build row). CI runs the same command (`.github/workflows/tests.yml:49`, `release.yml:125`).
- I confirmed that ruff 0.17.4 formats Python fences in every `.md` it checks, not only in the factory folder. Tracked `.md` files with Python fences today include `docs/extensions.md`, `.agents/skills/fastapi/**` and `.agents/skills/skill-creator/references/best-practices.md`. `release.md` and `learn.md` are committed by the next factory release (`factory.md:40`), so any Python fence in them reaches CI on another task's PR.
- The build live check's stop step left the server running. `web.pid` held the `cd && nohup` subshell (397497), and `uv` (397499) and the server (397507) kept running on 7455 until they were killed by PID (`build.md`, Shutdown). Verify then used `fuser -k 7456/tcp`.
- Some things worked well and are worth reusing:
  - plan's `ToolCatalog()` falsy trap
  - the sha256 characterization of tool-using bodies before and after the change (`1cfde406...` identical)
  - fix-1's sorted-JSON comparison when only key order changed
  - recording live wire payload keys through a traced session's `observability_events`

## Where the Workflow Broke Down
1. **Plan patched a fork instead of routing through its owner.** Triage handed the planner the root cause ("the fix never reached the copy"). The plan repeated the copy pattern, and review had to send it back. This was the only review loop and the reason verify needed a full live re-check rather than a smoke check.
2. **The format check was waived on a task-folder file.** Build reported checks-pass with a red repo-wide check, and the conductor patched it by hand. The same trap hits every stage file that pastes a Python script, including post-release files that land in a later task's PR.
3. **The scratch-server recipe records the wrong PID.** The skill's own stop command (`kill "$(cat "$S/web.pid")"`) does not stop the server. Only the build agent's manual check caught the leftover processes. An agent that trusted the recipe would leave port 74xx and the scratch-DB lease held.

## Customization Diagnosis
- Fork-vs-owner decision: the plan stage's framing is the gap, so the target is the **command** `.agents/commands/plan.md`. Triage already surfaced the fact (the investigator is fine), and the code-quality reviewer already has the rule ("Reuse canonical utilities instead of near-duplicates", "Duplicate helper logic where canonical owner should exist" in `code-quality-review.md`) and caught it. Adding a duplication check to the correctness `reviewer` would only duplicate the code-quality rule. The cheapest place to catch this is before build.
- Markdown fences and `ruff format`: two responsibilities.
  - The conductor owns the task folder; stage agents may not edit other stage files. So normalizing stage files is a **command** change in `.agents/commands/factory.md`.
  - "ruff formats Python fences in any `.md`" is a repo fact every session needs when writing docs or skills, so it goes in **`AGENTS.md`**.
- Scratch-server PID: a wrong step in a reusable procedure, so the target is the **skill** `.agents/skills/verify/SKILL.md`.

## Recommended Changes

### 1. Plan through the canonical owner when the bug is a fork
- **Target layer:** command (`.agents/commands/plan.md`, PHASE 2 Critical rules)
- **Change:** Add one bullet after "Prefer simplest plan that satisfies request and matches existing architecture.":
  > If triage or exploration shows the defect lives in a copy or override of a shared builder or helper that already has the correct behavior, plan to route the copy through the shared owner (delete the copy) rather than patching the copy. Plan the characterization for that change: compare serialized output with sorted keys if only key order can change. Patch the copy only when the shared owner cannot express the caller's difference, and record why.
- **Why:** triage stated the fork as root cause. Plan patched the copy anyway. `quality-1.md` sent it back as major, and fix-1 did what the plan could have specified (`self._protocol.build_request_body` plus `stream=False`, sorted-JSON identical).
- **Expected effect on next rep:** no review loop for this class of bug. The live check runs once on final source, and verify drops to a smoke check. This saves one fixer round, one validation rerun, one code-quality round and one full live check.

### 2. Conductor formats stage files before they can reach CI
- **Target layer:** command (`.agents/commands/factory.md`, Stage files / Task folder section)
- **Change:** Add:
  > Stage files are Markdown checked by `uv run ruff format --check .`; ruff formats Python fences inside them. After writing or receiving any stage file, the conductor runs `uv run ruff format .agents/factory/tasks/<id>/` (it only rewrites fenced Python code). Stage agents use `text` fences for command output and prefer a scratch-path reference over pasting whole scripts. A format-check failure confined to the task folder is the conductor's to fix, not a stage pass or fail; a failure anywhere else fails the stage.
- **Why:** build left `triage.md` unformatted and still reported checks-pass. The conductor fixed it by hand. `release.md` and `learn.md` are committed in a later task's release (`factory.md:40`), so an unformatted fence there would fail an unrelated PR's CI.
- **Expected effect on next rep:** the repo-wide format check is green at every stage with no ad-hoc fix. Stage agents get a clear rule instead of a waiver.

### 3. Record the Markdown-fence formatting in repo validation rules
- **Target layer:** `AGENTS.md` (Key Constraints, Validation by touched surface)
- **Change:** Add under the Python changes bullet:
  > `ruff format` (0.17+) also formats Python code fences in every Markdown file it checks (docs, skills, `.agents/**`), and CI runs `ruff format --check .`. After writing a `.md` with a Python fence, run `uv run ruff format <file>`; use a `text` fence for snippets that are not meant as formatted Python.
- **Why:** the trap is not factory-specific. Tracked fences already exist in `docs/extensions.md` and the `fastapi` / `skill-creator` skill references, so any docs or skill edit with a Python example can fail CI the same way.
- **Expected effect on next rep:** docs and skill edits format their fences before handoff, and nobody has to explain an unexpected "1 file would be reformatted" in a `.md`.

### 4. Make the scratch-server PID the real process and stop by port
- **Target layer:** skill (`.agents/skills/verify/SKILL.md`, Scratch server steps 3 and 7)
- **Change:** Replace the step 3 start command so `$!` is `uv` and not a `cd &&` subshell. Use `uv run --directory`, which sets the server cwd:
  ```text
  PBI_AGENT_SESSION_DB_PATH="$S/sessions.db" BROWSER=true nohup uv run --directory "$S/ws" --project <repo> pbi-agent web --port <p> --no-open > "$S/web.log" 2>&1 & echo $! > "$S/web.pid"
  ```
  Replace step 7 with:
  > Stop: `kill "$(cat "$S/web.pid")"` (uv forwards SIGTERM to the server), or `fuser -k <p>/tcp`. Then confirm both `! fuser <p>/tcp` and that `pgrep -af '[p]bi-agent web --port <p>'` prints nothing.

  Add a Gotcha:
  > `$!` after `cd X && nohup ... &` is the subshell, not the server; killing it leaves `uv` and the server running.
- **Why:** `build.md` Shutdown shows the recorded PID was the subshell and the server survived. I checked the replacement in this session: `nohup uv run --directory "$S" --project <repo> python3 ...` recorded the `uv` PID, the child ran with cwd `$S`, and `kill <uv pid>` also ended the child.
- **Expected effect on next rep:** the skill's own stop step works, no orphaned server holds port 74xx, and the post-stop check catches any leftover instead of relying on the agent noticing.

## Prompt / Skill / Command Mutations
- `plan.md` new Critical rules bullet: the exact text in change 1.
- `factory.md` stage-file formatting paragraph: the exact text in change 2.
- `AGENTS.md` validation note: the exact text in change 3.
- `verify/SKILL.md` step 3 command, step 7 and the new Gotcha: the exact text in change 4.

No change is proposed for the reviewers: `code-quality-review.md` already covers duplicated builders and caught this one. No profile change either. The gate counts for bug_fix review (2 `approved_unchanged`) and plan (1) are below the 5-row promotion threshold.

## Next Rep
1. Triage: reproduce offline as here, and name any fork of a shared helper as the root-cause class.
2. Plan: route forks through the owner (change 1), plan the sha256 or sorted-JSON characterization, and keep the `ToolCatalog()` falsy trap in the test plan.
3. Build: run the characterization before and after, plus the live check with the fixed verify recipe (change 4), and stop the server by PID or port with the post-stop check.
4. Conductor: run `uv run ruff format .agents/factory/tasks/<id>/` after each stage file (change 2), so the repo-wide check stays green.
5. Review: expect a clean first round. If no `fix-N` changed source, verify is a smoke check.

## Memory candidates
- Tool-less provider requests (Enhance prompt, compaction) must omit `tools`, tool choice and `parallel_tool_calls`. Every body builder now guards this when the tool list is empty. The Copilot chat path reuses `ChatCompletionsProtocol.build_request_body`, so do not reintroduce a forked body (gh-455). [verified 2026-11-20]
- An empty `ToolCatalog()` is falsy, so provider constructors fall back to the builtin registry. No-tools provider tests need `allowed_tools=()`, `tool_catalog=ToolCatalog()` and `assert provider._tools == []`. [verified 2026-11-20]
- Provider request-shape changes: prove that tool-using bodies are unchanged with a scratch sha256 dump of `json.dumps(body)` per builder, before and after. Use `sort_keys=True` when only key order may change. The live wire keys come from a traced session's `observability_events` `model_call` `request_payload`. [verified 2026-11-20]
- `ruff format --check .` (ruff 0.17.4) formats Python fences in Markdown, including committed factory stage files. Run `uv run ruff format <file>` on any `.md` with a Python fence. [verified 2026-11-20]
- Scratch server: `$!` after `cd X && nohup ... &` is the subshell. Start with `nohup uv run --directory <ws> --project <repo> ...` so `$!` is `uv`, which forwards SIGTERM to the server. [verified 2026-11-20]
- Follow-up (not done): the no-tools rule is now six separate guards across `openai_provider.py`, `xai_provider.py`, `google_provider.py`, `protocols/anthropic_messages.py`, `protocols/chat_completions.py` and `google_gcp_provider.py`. A parametrized cross-provider test ("no tool fields when tools are empty") would catch a new provider or fork that misses it. [unverified]

## Verdict
learn: 4 proposals
