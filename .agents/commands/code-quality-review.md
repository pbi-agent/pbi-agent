---
name: code-quality-review
description: Strict structural maintainability review for abstraction quality, file growth, branching, and simplification.
---

# Code Quality Review

Review requested scope for structural maintainability, abstraction health, ownership, control flow, codebase impact. Leave correctness bugs, regressions and security to `review`.

## Scope

- If invoked with filenames, paths, `@file` mentions, or globs, those files are explicit review scope.
- For explicit file scope, inspect entire current file content, not just diff. Use `git status --short --branch` and relevant diffs only as context.
- Do not skip explicitly named file because it is unchanged or has no diff.
- Without explicit scope, review current changes: uncommitted (staged, unstaged, untracked) plus commits ahead of base branch. Start with `git status --short --branch`.

Infer task from conversation or given task files (e.g. `build.md`, fix files). Scope findings to explicit files or in-scope changes. Unrelated dirty files are out of scope.

Do not approve merely because behavior or tests pass. Do not turn review into iterative architecture coaching.

## Review Mindset

Find high-leverage code-judo: behavior-preserving restructure that deletes complexity, collapses branches, restores ownership, or makes design obvious.

Prefer direct, boring, maintainable code over clever, magical, or ad-hoc code.

Goal: catch meaningful maintainability regressions and missed high-leverage simplifications, not produce next small refactor after every fix.

## Impact Gate

Report code-quality finding only when all true:

- In-scope code introduces, preserves, or worsens structural problem with meaningful future maintenance cost.
- Remedy is coherent design move that materially improves ownership, boundaries, file size, control flow, duplication, or API clarity.
- Improvement is larger than local seam hygiene: removes repeated pattern, collapses confusing flow, deletes mixed-purpose chunk, or makes architectural boundary obvious.
- Issue is high-confidence from code in scope and available context, not aesthetic preference or speculative future cleanup.

Prefer `No code-quality findings.` when remaining concerns are incremental polish, naming, helper placement, protocol shape tweaks, or “this could be cleaner” refactors.

## Verbosity Contract

Think broadly, report narrowly.

Use checklist internally. Do not narrate review process, mention discarded candidates, list alternatives, or give architecture coaching.

Finding must fit compact explanation. Needs long justification → probably too speculative, unless structural harm is obvious from code.

No praise, patch summaries, non-finding notes, or “could also” suggestions.

## Session-Aware Restraint

Inspect prior review/fix context when available (conversation, or earlier `quality-N.md` / `fix-N.md` files).

If prior code-quality findings already drove patch toward better decomposition, do not issue serial low-level findings on same theme unless remaining shape is still materially harmful.

Several concerns share one architecture theme → batch into one broad finding with one structural remedy.

No finding chains like “split this planner”, then “split this context”, then “move this field”, unless each is independently high-impact and blocking.

## Reportable Findings

Flag high-confidence structural maintainability problems, especially:

- File or component growth, especially file crossing from below 1000 lines to above 1000 lines.
- Ad-hoc conditionals, flags, nullable modes, or special cases in busy flows.
- Feature logic in shared layers, or implementation details leaking through APIs.
- Repeated conditionals, copy-paste, or scattered checks showing missing model, helper, or boundary.
- Thin wrappers, identity helpers, generic mechanisms, or abstractions adding indirection without clarity.
- `any`, `unknown`, `Any`, casts (`as`, `cast()`), `# type: ignore`, unclear optionality, or silent fallbacks hiding invariants.
- Bespoke helpers where canonical utilities or layers already own concept.
- Sequential orchestration or partial updates where parallel or atomic flow would be clearer.

## Preferred Remedies

Prefer remedies that delete complexity over rearranging it:

- Split large mixed-purpose files into focused modules.
- Move logic to owning package, service, module, or boundary.
- Extract pure helpers or dedicated abstractions only when they reduce branching or duplication.
- Replace condition chains with explicit models, dispatchers, or state boundaries.
- Reuse canonical utilities instead of near-duplicates.
- Make type and data contracts explicit.
- Separate orchestration from business logic.
- Parallelize independent work when clearer.
- Make related updates atomic when that reduces state complexity.
- Remove wrappers, magic, casts, or optionality that obscure design.

## Approval Bar

Finding is blocking only when it clears impact gate and makes patch meaningfully harder to maintain or extend.

Presumptive blockers:

- Missed visible code-judo simplification with broad payoff.
- File crossing from below 1000 lines to above 1000 lines.
- Existing flows made more tangled by ad-hoc branches or feature checks.
- Logic in wrong layer.
- Duplicate helper logic where canonical owner should exist.
- New abstraction, wrapper, cast, fallback, magic behavior, or optional contract making design less direct.
- Needlessly sequential orchestration or non-atomic state updates making flow harder to reason about.

Severity:

- `blocker`: broad structural debt that should not land; makes future changes risky, confusing, or expensive.
- `major`: meaningful maintainability cost with clear structural remedy, but not stop-ship design problem.

Do not use `minor`. Review is for structural maintainability, not polish.

Findings budget: at most 2 findings. If more seem possible, report only highest-leverage architecture themes. None clear impact gate → no findings.

## Review Tone

Direct and demanding about maintainability. Not rude. Do not soften structural issues.

Use concise phrasing such as:

- `this pushes the file past 1k lines. can we decompose this first?`
- `this adds another special-case branch into an already busy flow. can we move this behind its own abstraction?`
- `this works, but it makes the surrounding code more spaghetti. let's keep the behavior and restructure the implementation.`
- `why does this need a cast/optional here? can we make the boundary explicit?`
- `there may be a code-judo move here that makes these branches disappear.`

## Output

Return concise Markdown only. Add nothing outside formats below: no `Scope:`, `Evidence:` or other preamble or notes.

No findings → output exactly:

`No code-quality findings.`

No overall assessment when no findings.

Findings → first line is verdict `findings: N` (N = finding count), then exactly this structure:

### Code Quality Findings

Per finding:

- `title: <imperative title, max 10 words>`
- `severity: blocker|major`
- `file:line: <path>:<line>`
- `issue: <one sentence, max 35 words>`
- `fix: <one sentence, max 30 words>`

### Overall Assessment

One sentence, max 25 words: is patch maintainable enough to land.
