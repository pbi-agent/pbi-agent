---
name: fix-review
description: Fix Review Findings
---

# Fix Review Findings

Fix review findings. Ask no clarifying questions. Run no new general or code-quality review.

Findings source, first match wins:

1. Findings files named in request (factory: `review-N.md`, `quality-N.md`, `review-human-N.md`), plus extra items request adds.
2. Latest `/review` or `/code-quality-review` output in current conversation.

Treat source as truth. If it says `No findings.` or `No code-quality findings.`, change no code; report no findings to fix.

## Fixing findings

- Fix only listed findings.
- Accept these formats:
  - `/review` findings under `### Findings` with `priority`, `absolute_file_path`, `line_range`.
  - `/code-quality-review` findings under `### Code Quality Findings` with `severity`, `file:line`, maintainability explanation.
  - Human change requests (`review-human-N.md`): free text; each request = one finding.
- Use each finding's path, line/range, priority/severity, explanation to identify intended change.
- Line numbers can be stale after earlier fix rounds. Locate code by explanation.
- Verify each finding against code before editing. If code proves finding wrong, change nothing for it; report evidence.
- Fix each defect fully. If same wrong claim or pattern repeats elsewhere, grep; fix every occurrence or list ones left.
- Code-quality findings: keep intended behavior, apply requested cleaner structure. Not optional style feedback.
- Preserve unrelated user or workspace changes.
- No opportunistic refactors or style-only edits.
- Do not commit, push, merge, or open pull requests.

## Validation

After fixes, run focused validation for touched surface (`AGENTS.md`, Validation by touched surface). If validation cannot run, report why.

## Output

If request names output file, write full output there.

First line = verdict:

- `fix: done`: every finding fixed.
- `fix: partial`: any finding not fixed or disputed.

Then concise summary:

- findings fixed
- findings not fixed, with reason or evidence
- files changed
- validation run and results
