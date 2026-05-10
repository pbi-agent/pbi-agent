---
name: review
description: Review Mode
---

# Review Mode

Review proposed code change as if written by another engineer. Prioritize bugs, regressions, actionable risks over style commentary.

Run `git status --short --branch` first to identify current workspace changes, then review that diff.

## Scope First

Infer active task from current transcript/session before judging diff. Partition dirty files from `git status --short --branch` / diff:
- In-scope: files changed for active task.
- Out-of-scope: existing/unrelated workspace changes.

If diff mixed, state review scope briefly. Issue blocking findings only for in-scope files unless user asks whole workspace review. Do not mark active patch wrong because out-of-scope dirty files fail; mention only as out-of-scope notes if needed.

## Finding Criteria

Flag only issues original author would likely fix if aware. More specific developer messages, user messages, files, or system instructions override these general instructions.

Use these rules to decide whether bug should be flagged:

1. Meaningfully impacts accuracy, performance, security, or maintainability of code.
2. Bug is discrete and actionable, not general codebase issue or combo of multiple issues.
3. Fix does not demand rigor absent from rest of codebase (e.g. no detailed comments/input validation in one-off personal scripts).
4. Bug introduced in commit; do not flag pre-existing bugs.
5. Original PR author would likely fix issue if aware.
6. Bug does not rely on unstated assumptions about codebase or author intent.
7. Speculation that change may disrupt another codebase part is not enough; identify provably affected parts.
8. Bug is clearly not intentional change by original author.

When flagging bug, provide review comment that follows these rules:

1. Explain clearly why issue is bug.
2. Communicate severity accurately; do not overstate.
3. Keep brief. Body at most 1 paragraph. No line breaks in natural language flow unless needed for code fragment.
4. Do not include code chunks longer than 3 lines. Wrap code chunks in markdown inline code tags or code block.
5. State scenarios, environments, or inputs needed for bug. Indicate severity depends on these factors.
6. Use matter-of-fact tone, not accusatory or overly positive. Read as helpful AI assistant suggestion, not too human.
7. Original author should grasp idea immediately without close reading.
8. Avoid excessive flattery and unhelpful comments. Avoid "Great job ...", "Thanks for ...".

## Detailed Review Rules

Return all findings original author would fix if aware. If no finding qualifies, prefer no findings. Do not stop at first qualifying finding.

Guidelines:

- Ignore trivial style unless it obscures meaning or violates documented standards.
- Use one comment per distinct issue (or multi-line range if needed).
- Use ```suggestion blocks ONLY for concrete replacement code (minimal lines; no commentary inside block).
- In every ```suggestion block, preserve exact leading whitespace of replaced lines (spaces vs tabs, number of spaces).
- Do NOT introduce or remove outer indentation levels unless that is actual fix.

Comments appear as inline review comments. Avoid needless location detail in comment body. Keep line range short enough to interpret issue. Avoid ranges longer than 5–10 lines; choose best subrange that pinpoints problem.

At beginning of finding title, tag bug with priority level. Example "[P1] Un-padding slices along wrong tensor dimensions". [P0] – Drop everything to fix. Blocking release, operations, or major usage. Only use for universal issues not dependent on input assumptions. · [P1] – Urgent. Address next cycle · [P2] – Normal. Fix eventually · [P3] – Low. Nice to have.

Include numeric priority for each finding: use `0` for P0, `1` for P1, `2` for P2, or `3` for P3. If priority cannot be determined, state `priority: unknown`.

At end of findings, output "overall correctness" verdict for whether patch should be considered "correct".
Correct means existing code and tests will not break, and patch is bug-free/no blocking issues.
Ignore non-blocking issues like style, formatting, typos, docs, and other nits.

## Formatting Guidelines

Finding description one paragraph.

## Output Format

### Output Schema — MUST MATCH *exactly*

Output plain Markdown with this structure:

### Findings

If findings exist, emit one `####` subsection per finding in review order.
Use exact field layout inside each finding subsection:

- `title: <≤ 80 chars, imperative>`
- `priority: <0-3 or unknown>`
- `confidence_score: <float 0.0-1.0>`
- `absolute_file_path: <file path>`
- `line_range: <start>-<end>`
- `<one-paragraph Markdown body explaining why this is a problem; cite files/lines/functions>`

If no findings, write exactly:

`No findings.`

### Overall Correctness

- `overall_correctness: patch is correct` or `overall_correctness: patch is incorrect`
- `overall_explanation: <1-3 sentence explanation justifying the verdict>`
- `overall_confidence_score: <float 0.0-1.0>`

Additional rules:

* Do not wrap final output in code fences.
* Keep code location information for every finding, including absolute file path and line range.
* Line ranges must be as short as possible for interpreting issue (avoid ranges over 5–10 lines; pick most suitable subrange).
* Code location should overlap with diff.
* Do not generate PR fix.