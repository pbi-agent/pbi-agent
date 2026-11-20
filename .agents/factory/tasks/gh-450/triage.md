## Summary
Every markdown table is rendered by one component, `MarkdownContent`. It outputs a bare `<table>` (`min-w-full`, cells `whitespace-nowrap`) with no scroll wrapper of its own. So a wide table has nothing of its own to scroll in. Its width is handled by whatever scroll container is above it. That container is different on each surface: the whole assistant card, the whole file-preview pane, the whole dialog body. In the todo panel nothing scrolls sideways and the table is just clipped. Reproduced live in a browser on the exact session from the issue. The bug is real, has one root cause, and the fix belongs in `MarkdownContent`. Proceed.

## Findings

### Rendering (single source)
- `webapp/src/components/shared/MarkdownContent.tsx:197`: `tableClassName = "my-3 min-w-full border-collapse text-xs"`. There is no `max-width` and no wrapper. `min-w-full` only sets a minimum, so the table grows to the full width of its content.
- `MarkdownContent.tsx:370-383`: `th` and `td` both use `whitespace-nowrap`, which keeps cell text on one line (this behaviour must stay). A long cell therefore makes the table thousands of px wide. The issue's table measured 2632px.
- `MarkdownContent.tsx:367-369` (`baseMarkdownComponents.table`) renders the bare `<table>`. The non-copyable surfaces use it: settings preview, todo panel, thinking bodies and work-run messages.
- `MarkdownContent.tsx:404-410` (`copyableMarkdownComponents.table`) wraps the bare `<table>` in `CopyableSnippet kind="table"`. The copyable surfaces use it: assistant `TimelineEntry` and the file preview.
- `MarkdownContent.tsx:215-237` (`CopyableSnippet`) is `div.group/snippet.relative.*:my-0.my-3` with `overflow: visible`. Its width is the container width (1046px in the repro), but the table inside is 2632px, so the table overflows the snippet div.
  - The copy button sits in an `absolute top-2 right-2` overlay. It appears only on hover or focus-within (`group-hover/snippet` / `group-focus-within/snippet` opacity toggles, `:224`).
  - It is anchored to the snippet's right edge, which is the right edge of the visible card width, not of the table.
  - That snippet `<div>` is also the copy target that the TSV test checks.
- TSV copy: `tableChildrenToTsv` (`:150-158`) builds the text from React children, not from the DOM. Wrapping the `<table>` in another element changes neither the copy text nor its format.

### Why the assistant card "overflows" (confirmed in browser, master bundle built today)
Layout chain measured in Chrome, viewport 2320px, issue session `2efe3baa…` opened from a scratch copy of the session DB:

| element | width | scrollWidth | overflow-x |
| --- | --- | --- | --- |
| `table` | 2632 | 2631 | visible |
| snippet `div[data-markdown-copyable-snippet=table]` | 1046 | 2632 | visible |
| assistant card `div[data-timeline-content]` (`TimelineEntry.tsx:35-36`, `overflow-x-auto … px-5`) | 1088 | 2652 | **auto** |
| entry `div[data-timeline-entry]` | 1088 | 1088 | visible |
| timeline `mx-auto flex … w-full max-w-6xl flex-col` (`SessionTimeline.tsx:86`) | 1152 | 1152 | visible |
| scroll area `relative min-h-0 flex-1 overflow-y-auto` (`SessionTimeline.tsx:85`) | 2272 | 2257 | auto |
| panel inner / `#session-main` / group / section / sidebar main | 2272 | 2272 | hidden/auto |

- No ancestor gets wider, so the flex/grid `min-width:auto` problem does not apply on this surface.
  - `react-resizable-panels` Panel sets `minWidth:0` on the outer panel and `maxWidth:100%; overflow:auto` on the inner one (`node_modules/react-resizable-panels/dist/react-resizable-panels.js:2004-2040`).
  - `AppSidebar.tsx:108` has `min-w-0`, and the timeline is a stretch flex column.
  - Page and timeline `scrollWidth` equal their client width, so the page never scrolls sideways.
- **The scroll container is the whole assistant card** (`overflow-x-auto` added in `8728550d refactor-ui`), not the table. That causes the following, all confirmed:
  - The table is clipped at the card's padding box. The card's 20px right padding becomes overflow area, so the table has no right border or gutter and looks like it runs off the card edge and is cut. This matches the issue screenshot (zoom showed text cut mid-word at the card edge).
  - The only horizontal scrollbar is at the bottom of the card. For a long message it can be far below the table, even off-screen.
  - Scrolling sideways moves **all** card content. With `card.scrollLeft = 800`, the first paragraph moved from x=634 to x=-146. This breaks AC2 ("surrounding content does not move sideways").
  - The copy button scrolls with the content (x 1644 → 864 at scrollLeft 800). It is pinned to the right edge of the 1046px snippet, so it leaves the viewport once the card scrolls past about 1000px. This breaks AC4 ("visible and reachable while scrolled").

### Other surfaces (from code, not run in browser)
- File preview, `WorkspaceFileTreePanel.tsx:527-531`: `div.min-h-0.w-full.min-w-0.flex-1.overflow-auto > div.min-h-full.rounded-md.border.bg-card.p-4 > MarkdownContent copyable`.
  - The inner bordered card has no overflow setting, so a wide table paints **past the card's border**, and the outer pane scrolls sideways with all the content.
  - This is a true overflow past the card edge, and it breaks AC1 and AC5 for this surface (inferred from the CSS).
- Settings preview, `SettingsPreviewDialog.tsx:35`: `div.min-w-0.overflow-auto[data-settings-preview-content]` around a non-copyable `MarkdownContent`.
  - The whole dialog body scrolls sideways with the table, the same "everything moves" failure as the chat card.
  - The dialog body itself is `FieldGroup … overflow-y-auto` (`webapp/src/components/ui/form-dialog.tsx:75`, size `wide` = `sm:max-w-4xl` at `:52`) (inferred).
- Todo panel, `TodoPanel.tsx:314` (`div.min-w-0.text-sm[data-todo-content]`) inside `TodoPanel.tsx:380` (`min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto`).
  - A wide table is **clipped with no way to scroll**, so hidden columns cannot be reached (inferred from the CSS).
  - `TODO_MARKDOWN_COMPONENTS` overrides `li` etc. but not `table` (`TodoPanel.tsx:~196`), so the shared table renderer applies.
- Same root cause, not listed in the task (inferred):
  - Thinking bodies, `TimelineEntry.tsx:440` and `:472`, use `THINKING_BODY_CLASSES` with no overflow setting. The table would overflow the muted box and make the timeline scroll area (`overflow-y-auto`, which computes `overflow-x: auto`) scroll sideways. That would break AC2.
  - Work-run accordion messages, `SessionTimeline.tsx:1513-1514`, sit inside `AccordionPrimitive.Content` with `overflow-hidden` (`SessionTimeline.tsx:92-93`), so the table is clipped and cannot be scrolled.
  - A wrapper added inside `MarkdownContent` would fix both at no extra cost.

### What a fix has to satisfy (facts for the planner, not a design)
- The scroll container must be a per-table element between the `CopyableSnippet` and the `<table>`, or the table's own wrapper in base rendering, with `overflow-x-auto` and `max-width: 100%` / `min-width: 0`.
- The copy overlay must be positioned on an element that does **not** scroll: the `relative` snippet div, which must stay as wide as the container. Then the button stays at the visible top-right while the table scrolls under it.
- Nothing extra is needed for small tables. `overflow-x: auto` shows no scrollbar when content fits, and `min-w-full` keeps the current full-width look (AC3).
- The `*:my-0` / `my-3` margin handling on the snippet must still apply once a wrapper is added: the table's `my-3` is reset only for direct children.
- The card's own `overflow-x-auto` (`TimelineEntry.tsx:36`) can stay as a safety net. It just stops being the place where scrolling happens. Removing it is a planner choice and is outside the issue's "no layout changes beyond what is needed".

## Reproduction
Manual reproduction (done on master, bundle `src/pbi_agent/web/static/app` built 2026-11-20 12:53):
1. Copy the session DB to a scratch file with a read-only backup and clear `web_manager_leases` **in the copy only**. Then from `/home/drod/workspace/research-ml-v0` run `PBI_AGENT_SESSION_DB_PATH=<scratch>/sessions.db uv run --project /home/drod/workspace/pbi-agent pbi-agent web --port 7431 --no-open`.
2. Open `http://127.0.0.1:7431/sessions/2efe3baaa161465a962190e6f1edbaef`. The final assistant message contains the table "Question | Evidence from the workspace | My assessment".
3. Observed:
   - The table is cut at the card's inner right edge (no right border).
   - The horizontal scrollbar sits at the bottom of the card.
   - `card.scrollLeft = 800` moves paragraphs and the copy button 800px left.
   - In DevTools: `card.scrollWidth` 2652 > `clientWidth` 1086, `snippet.clientWidth` 1046 < `table.offsetWidth` 2632.

Generic reproduction without the private session: any assistant reply with a 3-column GFM table where one cell is about 400 characters long.

Failing Vitest outline (jsdom has no layout, so assert structure and classes, not geometry). Put it in `webapp/src/components/shared/MarkdownContent.test.tsx` (new `describe("MarkdownContent tables")`), plus one case in `TimelineEntry.test.tsx`:
1. `render(<MarkdownContent content={wideTable} />)` (base / non-copyable): `screen.getByRole("table").parentElement` is a dedicated scroll wrapper, e.g. it has a `data-markdown-table-scroll` attribute and the class `overflow-x-auto`. **Fails today**: the parent is the test container, and there is no wrapper.
2. `render(<MarkdownContent content={wideTable} copyable />)`:
   - The table's parent is the scroll wrapper (`overflow-x-auto`).
   - The wrapper's parent is `[data-markdown-copyable-snippet="table"]`.
   - The `Copy snippet` button is **not** inside the scroll wrapper (`expect(wrapper).not.toContainElement(button)`) and **is** inside the snippet.
   - **Fails today**: the table's parent is the snippet div.
3. Keep the existing TSV test passing (`TimelineEntry.test.tsx:316-332`, "copies rendered markdown tables as readable tsv snippets"). Optionally add a wide-cell version that asserts the full row text is copied.
4. Optionally check that `th`/`td` still have `whitespace-nowrap` (AC6 one-line cells) and the table still has `min-w-full` (AC3 look).
5. Optionally use surface smoke tests: `WorkspaceFileTreePanel.test.tsx`, `TodoPanel.test.tsx` and the `SettingsPage` preview test each assert that the table sits inside the scroll wrapper. A test in `MarkdownContent` covers them structurally.

Existing related tests:
- `TimelineEntry.test.tsx:316-332`: TSV copy of a table.
- `SessionTimeline.test.tsx:2669-2694`: assistant tables render as table elements.
- `MarkdownContent.test.tsx` has only link and run-in-terminal tests, no table tests.
- No tests on table layout or wrappers exist anywhere.

## Unknowns
- Whether to also remove the assistant card's `overflow-x-auto` (`TimelineEntry.tsx:36`). Low stakes; the planner can decide. Keeping it is safe and needs no change.
- The file preview, settings dialog and todo panel behaviour above is inferred from CSS, not run in a browser. The build/verify stage should confirm it visually (AC5) and check light and dark themes plus a narrow width (AC6).
- How the copy-button overlay should look over a horizontally scrolled table (it may cover the last visible cell's text). This is a visual detail for the planner or plan gate, not a human-blocking question.
- Dirty `TODO.md` (session checklist) and the untracked `.agents/factory/tasks/gh-450/` do not overlap the `webapp/` scope.

## Scope estimate
- Surfaces: frontend
- Likely files or areas:
  - `webapp/src/components/shared/MarkdownContent.tsx`: table wrapper in both the base and the copyable `table` renderers.
  - `webapp/src/components/shared/MarkdownContent.test.tsx`: new tests.
  - Possibly `webapp/src/components/session/TimelineEntry.test.tsx`.
  - Possibly a one-line class tweak in `TimelineEntry.tsx` or `WorkspaceFileTreePanel.tsx` if verification shows it is needed.
- Size: about 2-4 files, about 30-80 changed lines.

## Risk and profile
- risk: normal. No risk triggers apply: no API contracts, no dependencies, no `.agents/**`, and the diff is small.
- profile: keep `bug_fix`. Existing behaviour is wrong against intended containment, and the fix adds no new capability.

## Verdict
triage: proceed — reproduced live; there is one root cause (no per-table scroll wrapper in `MarkdownContent`, so the card, pane or dialog scrolls instead, or the table is clipped), and the fix is a small frontend change with a structural Vitest regression test.
