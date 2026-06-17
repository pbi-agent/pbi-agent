---
name: fix-review
description: Fix Review Findings
model_profile_id: worker-pro
allowed_tools: read,write,shell
---

# Fix Review Findings

Fix findings from previous `/review` or `/code-quality-review` turn in this
session.

Use latest review-like output in current conversation as truth. Ask no
clarifying questions. Do not run new general review or code-quality review.

If the latest relevant output says `No findings.` or
`No code-quality findings.`, make no code changes. Report no findings to fix.

## Fixing findings

- Fix only the listed findings.
- Accept either review format:
  - `/review` findings under `### Findings` with `priority`,
    `absolute_file_path`, and `line_range`.
  - `/code-quality-review` findings under `### Code Quality Findings` with
    `severity`, `file:line`, and maintainability explanation.
- Use each finding's file path, line/range, priority/severity, and explanation
  to identify intended change.
- For code-quality findings, preserve intended behavior while applying requested
  cleaner structure. Do not treat finding as optional style feedback.
- Preserve unrelated user or workspace changes.
- No opportunistic refactors or style-only edits.
- Do not commit, push, merge, or open pull requests.

## Validation

After fixes, run focused validation for touched surface.
If validation cannot run, report why.

Finish with concise summary:

- findings fixed
- files changed
- validation run and results
