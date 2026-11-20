# Verify gh-450

Merged code: `origin/master` 0584f031 (PR #453, commit 1a813bdd). Local `master` == `origin/master`; the source verified in the browser (pre-commit /verify, task.md Stage log) is byte-identical to the merged source.

## CI
- Tests on 0584f031: success. Deploy Docs on 0584f031: success. PR checks `test`, `terminal-windows`: success (release.md).

## Acceptance criteria
| AC | Evidence | Result |
| --- | --- | --- |
| 1 Wide table inside card, reachable by sideways scroll | `MarkdownContent.tsx:199-201,377-379,419-421` on master wraps every table in `MarkdownTableScroll` (`overflow-x-auto`). Browser (issue session, scratch DB): wrapper client 1046 / scroll 2632, scrolled to 800; wrapper rect inside card rect. Tests `MarkdownContent tables` (master `MarkdownContent.test.tsx:72-92`). | pass |
| 2 Timeline/content do not scroll or shift sideways | Card client 1086 == scroll 1086 (was 2652 on old master per build.md); document 2320 == 2320; paragraph x unchanged after scrolling the table. | pass |
| 3 Small table unchanged, no scrollbar | Test 3 (`min-w-full`, `whitespace-nowrap`, no vertical limit); build.md + review-1.md browser checks: small table full width, no scrollbar, screenshots match. | pass |
| 4 Copy action visible while scrolled; full TSV copy | Copy button outside the scroll wrapper (test 2 + browser `btnOutsideWrap: true`), button x unchanged after 800px scroll, visible on hover in screenshot. TSV: existing and new wide-table tests in `TimelineEntry.test.tsx` pass in CI. | pass |
| 5 File preview, settings dialog, todo panel | Shared renderer fix; build.md browser checks of all three surfaces: only the table scrolls. | pass |
| 6 Themes, narrow widths, styling unchanged | build.md: light + dark at ~800px and full width, theme tokens on `th`/`td`; cell/row classes untouched in the diff; review-1.md: 12px spacing unchanged. | pass |

## Issue
- #450 CLOSED (COMPLETED) via `Closes #450`.

verify: pass
