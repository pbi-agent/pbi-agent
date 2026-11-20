# Retrospective Report: gh-450 (wide markdown tables scroll inside their card)

## Outcome
Validated win. PR #453 merged as `0584f031`. PR checks and post-merge CI (Tests, Deploy Docs) are green, issue #450 is closed, and `verify.md` confirms all 6 acceptance criteria against merged `master`. This was the first `bug_fix` run. Every gate passed unchanged, each reviewer finished in one round, and nothing stepped back. The time that could have been saved went into repeating browser setup, not into fixing mistakes.

## Evidence from Trace
Sources: the task folder (all 8 files), the `task.md` working-tree diff, `.agents/factory/profiles.md`, `.agents/commands/factory.md`, `ledger.md`, `.claude/skills/verify/SKILL.md`, and issue #450 with its edit history (`gh api graphql … userContentEdits`). I did not query the session DB. The conductor ran in Claude Code, not the pbi-agent runtime, and every live server used a scratch DB copy, so the DB has no trace of this run (same situation as gh-449). The `pkill` incident is not in any task file; it comes from the conductor's own account.

- **Gates (`task.md` Gate log).**
  - intake, triage, plan, build and verify: `auto_pass`.
  - review and release: `approved_unchanged`, through the single combined question.
  - Risk stayed `normal` at every reassessment.
- **Review loops (Stage log).**
  - reviewer r1: `No findings.` (confidence 0.86).
  - code-quality r1: `No code-quality findings.`
  - There are no `fix-N` files, so the code that went through build, review and release is identical.
- **Last run's proposals held up.**
  - gh-449's learn proposals were all applied: Stage log split from Gate log, unpushed-commit check at intake, TODO rule, no nested sub-agents, and the pytest `-q` and flaky-test notes.
  - The Gate log now holds only the closed decision values, and release recorded "no unpushed base commits".
  - Full pytest passed on the first try (2526 passed, 9 skipped), with no flaky-test loop.
- **The same browser setup was built four times.**
  - **Triage** (`triage.md` Reproduction step 1): made a sqlite copy of `~/.pbi-agent/sessions.db`, cleared `web_manager_leases` in the copy, and ran `PBI_AGENT_SESSION_DB_PATH=<scratch> uv run --project <repo> pbi-agent web --port 7431 --no-open` from another workspace. It opened session `2efe3baa…` and measured widths with JS.
  - **Build** (`build.md` Manual browser check): the same DB-copy recipe, plus repointing the session to a scratch workspace with hand-made fixtures (`wide.md`, `TODO.md`, `.agents/skills/wide-table/SKILL.md`). Port 7463. It also had to work out two tricks: `window.resize` does not change `innerWidth` here, so it used a same-origin 800px iframe; and it set the theme via `pbi-agent-theme=light`. Its own follow-up note reads: "worth reusing for the verify stage".
  - **Review** (`review-1.md`): an independent render in headless Chromium with the shipped CSS (DPR 1/1.25/1.5, three widths). This was a different method that found something new (12px spacing kept), so it was not wasted.
  - **Release pre-commit `/verify`** (Stage log): the scratch DB and workspace again, port 7471. It re-measured the same numbers build had already recorded (wrapper 1046/2632, card 1086/1086) on identical code.
  - The `verify` skill covers only part of this. It mentions the lease and a scratch DB, but not the backup command, clearing the lease, repointing the session, fixtures, measurement snippets, iframe width, theme switching, or how to stop the server. It also lives only in `.claude/skills/verify/`. `.agents/skills/` has no `verify`, so pbi-agent-runtime stage agents cannot load it, even though `plan.md` tells them to "Use the `verify` skill".
- **The `pkill -f` self-kill (conductor account).**
  - While stopping a scratch server, the conductor ran `pkill -f` with a pattern that also appeared in its own `bash -c` command line.
  - `pkill` matched the conductor's shell and killed it (exit 144).
  - No written instruction covers stopping the server. `build.md` says "stopped it afterwards and confirmed port 7463 was free" but not how.
- **The static bundle had to be worked out from scratch.**
  - `plan.md` (Static bundle) derived from `.github/workflows/tests.yml:65-68` and `release.yml` that `src/pbi_agent/web/static/app` is tracked, that CI runs `git diff --exit-code` on it, and that it must be rebuilt with Bun 1.4.4.
  - This fact is only in `.agents/memory/tooling.md:6,12`. `AGENTS.md:68` says only that `web:build` writes the bundle there.
  - Build followed the plan correctly. The cost was planner research, not an error.
- **The operator rewrote the issue body.**
  - `release.md` says the body was "updated with original request quote, outcome, decisions, follow-ups". The edit history shows the original (12:15) and the rewrite (15:06).
  - This is exactly what `commit.md` step 7 asks for ("original request as quote, then outcome …"). The original text survives as a quote, and GitHub keeps the edit history.
  - Small losses: the original's trailing `🤖 Generated with Claude Code` line was dropped from the quote, and the factory review comment (14:54) is now the only place the review text lives.

## Where the Workflow Broke Down
1. **The browser setup was rebuilt by hand in each stage** (triage, build, pre-commit verify), each agent working out the lease, DB copy, fixtures and width/theme tricks again. This was the main time loss in an otherwise clean run.
2. **Fully re-verifying code that had not changed.** The pre-commit `/verify` repeated build's whole measurement pass, although no `fix-N` existed and `verify.md` itself relies on "source byte-identical".
3. **Fragile process cleanup.** No recipe gives a safe stop step, so a common shell habit killed the conductor's shell.
4. Not a breakdown: the issue-body rewrite worked as designed. One ordering hazard remains. The body says "Shipped" before verify runs, so if verify fails and the task goes back to triage, the issue already reads as done. This is acceptable for now because `Closes #N` closes the issue on merge anyway.

## Customization Diagnosis
| Issue | Layer | Why this layer |
| --- | --- | --- |
| Scratch-DB browser recipe rebuilt in each stage | skill (`verify`) | A reusable multi-step validation procedure, needed only for web/UI work. Too detailed for `AGENTS.md`, and not limited to one stage. |
| `pkill -f` self-kill when stopping the server | skill (`verify`) | It happened during the skill's stop step; the fix is a concrete stop procedure inside the recipe. The general fact goes to memory. |
| Repeated full browser checks on unchanged code | command (`factory.md`) | The conductor owns which stage produces evidence and when that evidence can be reused. |
| Tracked static bundle and CI drift check | `AGENTS.md` | A repo rule every frontend session needs, factory or not. Today it is only in a topic memory page. |
| Issue body rewrite | none | It followed `commit.md` step 7 and kept the original. A change is a human preference (e.g. post the outcome as a comment instead), not a fault this run showed. |

## Recommended Changes

### 1. Make `verify` a shared skill and add the scratch-server recipe
- **Target layer:** skill (`.agents/skills/verify/SKILL.md`, made canonical, with `.claude/skills/verify` turned into a symlink to it so both runtimes load the same file)
- **Change:** Add a "Scratch server" section covering:
  - a consistent DB copy, clearing the lease in the copy, and optionally repointing a session to a scratch workspace;
  - a standard fixture workspace (wide and small markdown table in `wide.md`, `TODO.md`, and a skill), so all markdown surfaces work in one server;
  - a non-default port, a start command that records the PID, and a probe;
  - JS measurement snippets (`clientWidth`/`scrollWidth`, `scrollLeft`, element x before and after);
  - narrow widths via a same-origin iframe, and theme via the `pbi-agent-theme` localStorage key on the scratch origin only.

  The draft is below.
- **Why:** Triage, build and the conductor each rebuilt this (`triage.md` Reproduction step 1, `build.md` Manual browser check setup and §5, Stage log pre-commit row). `build.md` asked for it to be reused. `plan.md` points stage agents at a skill that `.agents/skills/` does not contain.
- **Expected effect on next rep:** Faster, since each UI stage starts measuring right away. More reliable, since every run uses the same fixtures and measurements, which makes before/after numbers comparable. Works under both runtimes.

### 2. Stop scratch servers by PID or port, never `pkill -f` with a self-matching pattern
- **Target layer:** skill (`verify`, Gotchas plus the recipe's stop step)
- **Change:** Add: "Stop the scratch server with `kill "$(cat <scratch>/web.pid)"`, or by port (`fuser -k <port>/tcp`), then confirm the port is free. Never `pkill -f <pattern>` when the pattern appears in the same command line. It matches the invoking `bash -c` and kills your own shell (exit 144). If a pattern kill is unavoidable, use the bracket trick (`pkill -f '[p]bi-agent web --port 7471'`). Never stop the user's own server (often 7424)."
- **Why:** The conductor's shell was killed by its own `pkill -f` while stopping the port-7471 server, and no stage file says how servers were stopped.
- **Expected effect on next rep:** Cleanup can no longer kill the conductor or a stage agent, and stopping the server is a check that is recorded.

### 3. Reuse browser evidence per code state
- **Target layer:** command (`.agents/commands/factory.md`, Review and Release stage notes)
- **Change:** Add to the Review note: "Live UI evidence is produced at triage (reproduce on base) and build (after the change), using the `verify` skill recipe. Reviewers reuse `build.md` measurements and run only targeted checks for claims they doubt." Add to the Release note: "If a pre-commit verify is required and no `fix-N` changed source since `build.md`'s browser check, make it a smoke check of the primary acceptance criterion with the build fixtures (one measurement, one screenshot), recorded in the Stage log. If source changed after build, rerun the full check."
- **Why:** Build and release measured the same numbers on identical code (no `fix-N`). `verify.md` already relies on "byte-identical" source rather than a new check. The reviewer's targeted headless check is the model to follow: it added new evidence instead of repeating old evidence.
- **Expected effect on next rep:** One full browser pass less per UI task, with the same coverage. Re-verification stays mandatory whenever the code changes.

### 4. Record the tracked static bundle in `AGENTS.md`
- **Target layer:** `AGENTS.md` (Architecture Snapshot, Frontend bullet, or the Validation list in Key Constraints)
- **Change:** Add: "`src/pbi_agent/web/static/app` is tracked in git; any `webapp/` source change must include the bundle rebuilt with `bun run web:build` under the CI-pinned Bun (1.4.4). CI runs `git diff --exit-code` on it, and a Node-run Vite build gives different chunk hashes."
- **Why:** `plan.md` had to derive this from two workflow files. It exists only in `.agents/memory/tooling.md`, which is not preloaded as detail. A non-factory frontend session would miss it, and CI would fail.
- **Expected effect on next rep:** The planner skips the research and no frontend change ships without its bundle. This keeps working as frontend work changes.

## Prompt / Skill / Command Mutations

**`.agents/skills/verify/SKILL.md`: new section (after Launch):**
```markdown
## Scratch server (reproduce / verify UI on real or fixture sessions)
1. Scratch dir `S` (session scratchpad). Consistent DB copy, never touch the original:
   `python3 -c "import sqlite3,sys; s=sqlite3.connect(f'file:{sys.argv[1]}?mode=ro',uri=True); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.execute('DELETE FROM web_manager_leases'); d.commit()" ~/.pbi-agent/sessions.db "$S/sessions.db"`
2. Fixture workspace `$S/ws` for markdown surfaces: `wide.md` (3-column table, one ~400-char cell, plus a 2-column small table), `TODO.md` (same wide table), `.agents/skills/wide-table/SKILL.md` (frontmatter + wide table). To open a real session against it, in the COPY only: `UPDATE sessions SET directory=lower('<abs $S/ws>') WHERE session_id=?`.
3. Start from the fixture workspace on a free non-default port (e.g. 74xx), record the PID:
   `cd "$S/ws" && PBI_AGENT_SESSION_DB_PATH="$S/sessions.db" uv run --project <repo> pbi-agent web --port <p> --no-open & echo $! > "$S/web.pid"`; probe `curl -fsS http://127.0.0.1:<p>/api/bootstrap`. Rebuild with `bun run web:build` first; check server start time vs. last build.
4. Measure with JS (record `client/scroll` widths): table, `[data-markdown-table-scroll]`, `[data-markdown-copyable-snippet]`, `[data-timeline-content]`, timeline scroll area, `document.documentElement`. Containment check: set `scrollLeft` on the inner scroller, confirm ancestors' `scrollLeft` stay 0 and sibling element x is unchanged.
5. Narrow width: `window.resize` does not change `innerWidth` here; load the page in a same-origin `<iframe style="width:800px">` and measure inside it.
6. Theme: `localStorage.setItem('pbi-agent-theme','light'|'dark')` on the scratch origin, reload; reset to `system` after.
7. Stop: `kill "$(cat "$S/web.pid")"` (or `fuser -k <p>/tcp`), confirm the port is free. Record port, fixtures and numbers in the stage file.
```

**`.agents/skills/verify/SKILL.md`, Gotchas: add:**
```markdown
- Never `pkill -f <pattern>` with a pattern that appears in the same command line: it matches the invoking `bash -c` and kills your own shell (exit 144). Stop by PID file or port; if a pattern is unavoidable use `pkill -f '[p]bi-agent web --port <p>'`.
```

**`factory.md`, Review stage note: append:**
```markdown
UI evidence: triage reproduces on base and build verifies the change, both with the `verify` skill's scratch-server recipe. Reviewers reuse `build.md` measurements and run only targeted checks for claims they doubt.
```

**`factory.md`, Release stage note: append:**
```markdown
If a pre-commit verify is required and no `fix-N` changed source since the browser check in `build.md`, run it as a smoke check of the primary acceptance criterion with the build fixtures and log it in the Stage log; otherwise rerun the full check.
```

**`AGENTS.md`, Architecture Snapshot, Frontend bullet: append:**
```markdown
The bundle in `src/pbi_agent/web/static/app` is tracked: include it, rebuilt with `bun run web:build` under the CI-pinned Bun (1.4.4), with any `webapp/` source change; CI fails on `git diff --exit-code` drift (a Node-run Vite build changes chunk hashes).
```

## Next Rep
1. **Intake:** as this run did (unpushed check, dirty files, profile from labels).
2. **Triage:** reproduce with the `verify` skill's scratch server and fixture workspace, and record the baseline numbers.
3. **Plan:** reference the skill recipe and the tracked bundle rule (from `AGENTS.md`) instead of deriving them.
4. **Build:** regression tests fail first, then pass. Run the full browser matrix once with the same fixtures, and record the numbers next to the triage baseline.
5. **Review:** independent targeted checks only, as in `review-1.md`.
6. **Release:** if the code is unchanged since build, a smoke verify. Stop the server by PID.
7. **Verify:** reuse evidence tied to the merged SHA, as `verify.md` did.

## Memory candidates
- First `bug_fix` factory run (gh-450, PR #453, 2026-11-20) completed under a Claude Code conductor. All gates were unchanged, each reviewer took 1 round, and there were no reruns. The gh-449 learn proposals (Stage log, unpushed-commit check, TODO rule, flaky-test and `-q` notes) were applied and held. [verified 2026-11-20]
- `pkill -f <pattern>` kills the calling shell when the pattern appears in its own command line (exit 144 in the conductor). Stop servers by PID file or port. [verified 2026-11-20, conductor-reported]
- UI layout checks in this Chrome environment: `window.resize` does not change `innerWidth`, so use a same-origin fixed-width iframe. The theme is the `pbi-agent-theme` localStorage key. [verified 2026-11-20]
- Gate promotion: nothing is eligible. `bug_fix` review and release each have 1 `approved_unchanged` row, and every `build` gate has 1; 5 in a row are needed.

## Verdict
learn: 4 proposals
