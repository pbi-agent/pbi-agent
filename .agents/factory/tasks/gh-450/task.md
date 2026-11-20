---
id: gh-450
type: bug_fix
type_reason: Label bug (+ui); wide markdown tables overflow their card, existing behavior wrong vs intended containment, no new capability.
source: https://github.com/pbi-agent/pbi-agent/issues/450
risk: normal
risk_triggers: none
stage: done
status: done
---
# Keep wide markdown tables inside the message card, with horizontal scrolling

## Goal
A markdown table wider than its container scrolls sideways inside its own area, within the width of its message card or panel, on every surface that renders markdown (session timeline chat messages, workspace file preview, settings preview dialog, todo panel). The timeline, card and page never scroll horizontally because of a table. Full requirements and scope: issue #450 (`gh issue view 450 --json body`).

## Acceptance criteria
1. A wide table (e.g. three columns with a long "Evidence from the workspace" column) sits entirely inside the assistant card's borders; hidden columns are reachable by scrolling sideways inside the table area.
2. With a wide table on screen, the timeline does not scroll horizontally and surrounding content does not move sideways.
3. A small table renders the same as before and shows no scrollbar.
4. Hovering or focusing a wide table in a chat message shows the copy action (visible and reachable while the table is scrolled sideways), and copying still produces the full table as tab-separated text.
5. A wide table in the file preview panel and in the settings preview dialog (and the todo panel) is also contained and scrolls sideways.
6. Behavior holds in light and dark themes and at narrower window widths; existing table styling (borders, header background, striped rows, spacing, theme colors) is unchanged; cell text stays on one line; tall tables still grow vertically.

Out of scope: wrapping/truncating cell text, vertical table scrolling/height limits, sticky headers, changes to table content, copy format or other markdown elements, page/chat layout changes beyond what is needed to contain tables.

## Links
- Issue: https://github.com/pbi-agent/pbi-agent/issues/450
- Frontend: `webapp/src/` (markdown rendering component, styles in `webapp/src/styles/`)

## Environment notes (intake)
- Branch `master`, clean tree, in sync with origin/master (no unpushed commits).
- Conductor runs in Claude Code: stage agents are Agent-tool sub-agents told to follow `.agents/agents/<name>.md` and its referenced `.agents/commands/<cmd>.md`.

## Stage files
- task: task.md
- triage: triage.md
- plan: plan.md
- build: build.md
- review: review-1.md
- quality: quality-1.md
- release: release.md
- verify: verify.md
- learn: learn.md

## Gate log
| stage | gate | decision | note |
| --- | --- | --- | --- |
| intake | always_run | auto_pass | type bug_fix (label bug), risk normal |
| triage | auto | auto_pass | triage: proceed; reproduced live; root cause = no per-table scroll wrapper in MarkdownContent; risk stays normal |
| plan | auto | auto_pass | plan: ready; all 6 AC + reproduce/regression_test mapped; static bundle tracked, rebuild with bun |
| build | always_run | auto_pass | conductor reran test:web (894 passed), lint, typecheck, web:build (deterministic hashes): green; risk stays normal (3 src/test files + generated bundle, <200 lines) |
| review | approve | approved_unchanged | human: Approve and release |
| release | approve | approved_unchanged | human: Approve and release; no unpushed base commits |
| verify | always_run | auto_pass | verify: pass; CI green on 0584f031; all 6 AC confirmed; #450 closed |
| learn | always_run | auto_pass | learn: 4 proposals; ledger rows appended; no gate eligible for promotion |

## Stage log
| stage | round | result | note |
| --- | --- | --- | --- |
| review | reviewer r1 | No findings. | copy overlay outside scroller; spacing 12px unchanged (headless Chromium); targeted tests/lint/typecheck rerun |
| review | code-quality r1 | No code-quality findings. | agent reviewers clean; awaiting human review+release gate |
| release | validation | pass | ruff/format/basedpyright clean; full pytest 2526 passed, 9 skipped; test:web 894 passed; lint, typecheck, web:build ok (bundle deterministic) |
| release | pre-commit /verify | pass | scratch DB+workspace, port 7471: issue session wrapper 1046/2632 scrolled 800px, card 1086/1086, doc not widened, copy button + paragraphs did not move, button visible on hover; server stopped |
| release | operator | release: shipped | PR #453 merged 0584f031; PR checks + post-merge CI green; issue closed |

Learn proposals 1-4 applied on human request (2026-11-20), plus: verify moved before release; issue updates reduced to one brief final comment (or a comment when blocked).
