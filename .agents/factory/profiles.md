# Factory Profiles

Read by `/factory` at intake. The pipeline is fixed; a profile only sets how strict each gated stage is and which checks the build must prove. To add a kind of work, add a profile here, not a new pipeline. Humans own this file: agents propose changes in `learn.md`, they never edit it.

## Profiles

```yaml
gates: auto | approve | skip     # auto = passes when the exit check passes; approve = a human must say yes
always_run: [intake, build, verify, learn]

profiles:
  docs:
    triage: skip
    plan: skip
    review: auto
    release: auto
    reviewers: [reviewer]
    checks: [links, style]
  bug_fix:
    triage: auto
    plan: auto
    review: approve
    release: approve
    reviewers: [reviewer, code-quality-reviewer]
    checks: [reproduce, regression_test]
  build:
    triage: approve               # is it worth doing?
    plan: approve                 # is the design right?
    review: approve
    release: approve
    reviewers: [reviewer, code-quality-reviewer]
    checks: [acceptance_tests, docs]
```

## Detection

The conductor picks the profile itself and never asks the human for it. It records `type` and a one-line reason in `task.md`.

Signals, in order: issue labels, request wording, expected surface.

- `docs`: label `documentation`, or the change is confined to `docs/**`, `README.md`, or changelog prose, with no behavior change. `.agents/**`, `AGENTS.md` and `MEMORY.md` are not docs.
- `bug_fix`: label `bug`, or existing behavior is wrong against documented or intended behavior and the fix adds no new capability.
- `build`: labels `enhancement` or `feature`, and everything else (features, enhancements, refactors, dependencies, tooling). Default when unsure.

Strictness order is `docs` < `bug_fix` < `build`. When triage, plan or the real diff shows the work is a stricter type, reclassify upward and apply the stricter gates to every stage not yet passed. Never reclassify downward within a task.

## Risk

`risk` is `normal` or `high`. Assess at intake and again after triage, plan and build (against the real diff). Risk only raises: once `high`, it stays `high` for the task.

`high` when any of these is touched or true:

- Provider request paths: `src/pbi_agent/providers/`
- Shell tool, workspace confinement, file-tool path validation: `src/pbi_agent/tools/shell.py`, `src/pbi_agent/tools/workspace_access.py`
- Hooks trust, sandbox
- Session DB schema or persistence: `src/pbi_agent/session_store.py`
- Web API contracts: routes, schemas, `webapp/src/api.ts`, `webapp/src/types.ts`
- CI and release workflows, packaging, dependencies: `.github/workflows/`, `pyproject.toml`, `uv.lock`, `package.json`, `bun.lock`
- Factory design: `.agents/**`, `AGENTS.md`
- Diff over about 15 files or 500 changed lines
- Triage verdict `needs-human`, or unknowns left unresolved

Effect: every `auto` gate becomes `approve`. Record the triggers in `task.md`.

## Checks

Every profile also runs the surface validation from `AGENTS.md` (Python, frontend, docs) for the surfaces it touched.

| Check | Passes when |
| --- | --- |
| `links` | `bun run docs:build` passes. |
| `style` | The page matches neighbouring docs: frontmatter `title` and `description`, heading and tone conventions. Judged by the reviewer. |
| `reproduce` | A failing test, or an exact command with its output, shows the bug before the fix. Recorded in `triage.md` or `build.md`. |
| `regression_test` | That test is in the diff and passes, and the full suite for the touched surface passes. |
| `acceptance_tests` | Each acceptance criterion in `task.md` maps to a test or a recorded verification in `build.md`. |
| `docs` | A user-visible behavior change updates `docs/` and `bun run docs:build` passes, or `build.md` states why no docs change is needed. |

## Gate promotion

The ledger at `.agents/factory/tasks/ledger.md` holds one row per gate decision. When one profile and stage shows 5 consecutive `approved_unchanged` rows, the conductor proposes `approve → auto` in its handoff. A human makes the edit here.
