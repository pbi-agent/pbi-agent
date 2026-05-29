---
name: fix-review
description: Fix Review Findings
model_profile_id: worker
allowed_tools: read,write,shell
---

# Fix Review Findings

Fix findings from the previous `/review` turn in this session.

Use the latest review output in the current conversation as the source of truth.
Do not ask clarifying questions and do not perform a new general review.

## Fixing findings

- Fix only the listed findings.
- Use each finding's file path, line range, priority, and explanation to identify
  the intended change.
- Preserve unrelated user or workspace changes.
- Do not make opportunistic refactors or style-only edits.
- Do not commit, push, merge, or open pull requests.

## Validation

After making fixes, run the focused validation appropriate for the touched surface.
If validation cannot be run, report why.

Finish with a concise summary of:

- findings fixed
- files changed
- validation run and results
