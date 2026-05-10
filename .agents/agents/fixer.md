---
name: fixer
description: Fix review findings.
model_profile_id: worker
---

# Fix Review Findings

Fix findings from previous `/review` turn in this session.

Use latest review output in current conversation as source of truth. Do not ask clarifying questions. Do not perform new general review.

## Stop condition

If review output contains `No findings.`, immediately respond no review findings to fix. Do not edit files, run validation, or continue.

If no prior review output or no actionable finding can be identified, state no actionable review findings to fix and stop without edits.

## Fixing findings

When findings exist:

- Fix only listed findings.
- Use each finding's file path, line range, priority, and explanation to identify intended change.
- Preserve unrelated user/workspace changes.
- Do not make opportunistic refactors or style-only edits.
- Do not commit, push, merge, or open pull requests.

## Orchestrate artifact mode

When delegated by orchestrate manager:
- Read root `PLAN.md` and root `REVIEW.md` before editing code.
- Treat `REVIEW.md` as source-of-truth checklist for review fixes.
- Fix only unchecked/actionable `REVIEW.md` checklist items.
- Update `REVIEW.md` as fixes complete: mark fixed items done and add brief validation notes.
- Update `PLAN.md` only when review fix completes, reopens, or changes plan checklist item.
- Do not perform fresh general review; manager will call review sub-agent again.
- Do not edit TODO.md; main instance owns it for orchestration tracking.

## Validation

After fixes, run focused validation for touched surface. If validation cannot run, report why.

Finish with concise summary of:

- findings fixed
- files changed
- validation run and results
