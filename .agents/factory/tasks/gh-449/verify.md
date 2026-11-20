## Verify (conductor, 2026-11-20)

Merged master `2e68f9a6` (PR #451); local `src/ tests/ docs/` identical to `origin/master`.

| AC | Evidence on merged master | Result |
| --- | --- | --- |
| 1 `--doc` everywhere | Walked `build_parser()`: 56 paths (root + 55). `pbi-agent <path> --doc` with fresh `HOME`: 0 failures, all non-empty, rc 0 | pass |
| 2 missing guide caught | `tests/cli/test_doc.py` guard tests (fake subparser without guide fails) pass; CI Tests green | pass |
| 3 no args / no config / no side effects | `test_doc.py` side-effect tests pass; pre-commit live check: `--doc`, `web --doc` start no server, ~0.3s, empty stderr; only `sessions.db` created (accepted `--help` parity at triage) | pass |
| 4 guide content | Section/heading + parent-lists-children + forward/reverse option sync + usage-match tests pass; reviewer sampled ~17 guides against code (review-1/2) | pass |
| 5 `--help` mentions `--doc` | `pbi-agent --help`: 3 matches; `pbi-agent kanban --help`: 2 matches | pass |
| 6 docs | `docs/cli.md:14` "Built-in Guides (`--doc`)"; Deploy Docs run on `2e68f9a6` success | pass |
| 7 behavior/help unchanged | 56-path before/after help diff (build.md, independently redone in review-1): only `--doc` additions; `tests/cli` 591 passed | pass |

- CI on `2e68f9a6`: Tests success, Deploy Docs success.
- Issue #449: CLOSED (completed) by PR #451; body updated by operator.

verify: pass
