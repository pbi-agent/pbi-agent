# Plan: per-table horizontal scroll wrapper for markdown tables (gh-450)

## Summary
Every markdown table comes from `MarkdownContent`, which renders a bare `<table>` (`min-w-full`, `nowrap` cells). Because the table has no scroll container of its own, the nearest ancestor scrolls instead (the assistant card, the file-preview pane, the dialog body), or the table is simply clipped (todo panel, work-run accordion).

The fix wraps each table in a dedicated `overflow-x-auto` div inside `MarkdownContent`. This is done in both the base renderer and the copyable renderer. In the copyable case the wrapper sits between the `relative` `CopyableSnippet` div and the `<table>`. The copy overlay stays a sibling of the wrapper, so the overlay does not scroll and stays at the snippet's visible top-right while the table scrolls under it. This is one root cause with one fix point, and it covers chat, file preview, the settings dialog and the todo panel. It also fixes thinking bodies and work-run messages at no extra cost.

There are no API, type or contract changes. Only frontend files change, plus the rebuilt static bundle.

## Key changes (`webapp/src/components/shared/MarkdownContent.tsx`)
- **Table scroll wrapper.** Add a small internal `MarkdownTableScroll` component that renders the following around the `<table>`:
  `<div className="my-3 max-w-full min-w-0 overflow-x-auto" data-markdown-table-scroll="">`
  - Move the vertical margin from the table to the wrapper: `tableClassName` becomes `"min-w-full border-collapse text-xs"` (drop `my-3`). Inside a scroll container, margins no longer collapse with the surrounding text. Keeping `my-3` on the table would add about 12px of extra inner gap above and below and change spacing. With the margin on the wrapper, spacing outside the snippet stays the same as today.
  - `min-w-full` stays on the table, so small tables still fill the width and show no scrollbar (`overflow-x: auto` only shows a scrollbar when the table overflows).
  - Keep every `th`/`td`/`tr` class unchanged: borders, `bg-muted` header, `even:bg-muted/40` stripes, padding, `whitespace-nowrap`.
  - Add no height limit and no vertical overflow setting, so tall tables keep growing vertically.
- **Base renderer** (`baseMarkdownComponents.table`). Return `<MarkdownTableScroll><table className={tableClassName}>…</table></MarkdownTableScroll>`. Surfaces that use it: settings preview, todo panel, thinking bodies, work-run messages.
- **Copyable renderer** (`copyableMarkdownComponents.table`). Return `<CopyableSnippet kind="table" text={tableChildrenToTsv(children)}><MarkdownTableScroll><table …/></MarkdownTableScroll></CopyableSnippet>`.
  - The wrapper is a direct child of the snippet, so the snippet's `*:my-0` resets the wrapper's `my-3`. The snippet's own `my-3` then gives exactly today's spacing.
  - Do not change `CopyableSnippet`. Its overlay (`absolute top-2 right-2 z-10`, shown on hover or focus-within) is already a sibling rendered before the children. It is positioned against the non-scrolling `relative` snippet, which is as wide as the container. So the button stays visible at the visible top-right while the table scrolls, and both hover and focus inside the scrolled table still reveal it.
  - The copy text is unchanged. `tableChildrenToTsv` reads the React `children` passed to `table`, not the DOM, so the wrapper cannot change it.
  - When a table is nested inside another copyable snippet (for example inside a blockquote or list), `CopyableSnippet` passes its children through. The table still gets its scroll wrapper.
- **No layout changes elsewhere.** Keep the assistant card's `overflow-x-auto` (`TimelineEntry.tsx:36`) as a harmless safety net. Once tables scroll in their own wrappers it never activates for tables. Do not change `WorkspaceFileTreePanel`, `SettingsPreviewDialog` or `TodoPanel`. Triage showed that each of their containers is a normal block or `min-w-0` chain, so a `max-w-full` block wrapper takes the container width. Touch one of them only if the manual check below shows a surface that still overflows, then record the change in `build.md`.

## Test plan

### Reproduce + regression test (profile checks `reproduce`, `regression_test`)
Add `describe("MarkdownContent tables")` to `webapp/src/components/shared/MarkdownContent.test.tsx`. jsdom has no layout, so the tests check structure and classes. Use a wide fixture: a 3-column GFM table, `| Question | Evidence from the workspace | My assessment |`, where one cell is about 400 characters long.

The builder must run tests 1 and 2 **before** the source change, confirm they fail, and record the failing output in `build.md` (this satisfies `reproduce`).

1. **Base table has its own scroll wrapper (fails today).** Render `<MarkdownContent content={wide} />`.
   - `screen.getByRole("table").parentElement` has the attribute `data-markdown-table-scroll` and the class `overflow-x-auto`.
2. **Copyable table: wrapper inside snippet, copy action outside wrapper (fails today).** Render `<MarkdownContent copyable content={wide} />`.
   - The table's parent is the scroll wrapper.
   - The wrapper's `parentElement` matches `[data-markdown-copyable-snippet="table"]`.
   - The `Copy snippet` button is inside the snippet, and `expect(wrapper).not.toContainElement(button)`.
3. **Full-width look and one-line cells are preserved.**
   - The table has class `min-w-full`.
   - Every `columnheader` and `cell` has class `whitespace-nowrap`.
   - The wrapper has no `overflow-y`/`max-h` class (no vertical limit). Assert that its class list does not contain `max-h-` or `overflow-y-`.
4. **Wide-table copy gives the full TSV.** In `webapp/src/components/session/TimelineEntry.test.tsx`, add a case next to the existing "copies rendered markdown tables as readable tsv snippets" (`:315`). It renders an assistant message with the wide table, clicks `Copy snippet`, and asserts `writeText` was called with the full tab-separated text, including the long cell unchanged.
   - The existing TSV test must keep passing unchanged.

### Acceptance criteria mapping
| AC | Proof |
| --- | --- |
| 1 Table inside the card, sideways scroll inside the table area | Tests 1-2 (structure). Manual check: chat card shows the table's right border/gutter, and the scrollbar sits directly under the table. |
| 2 Timeline does not scroll sideways; surrounding text does not move | Manual check: with the table scrolled, `card.scrollWidth === card.clientWidth` and the paragraph x positions do not change. |
| 3 Small table looks the same, no scrollbar | Test 3 (`min-w-full`). Manual check: a 2-column table has no scrollbar and the same spacing as before. |
| 4 Copy action visible and reachable while scrolled; full TSV | Test 2 (button outside the scroll element). Test 4 plus the existing TSV test. Manual check: hover or tab into the table at `scrollLeft` > 0 shows the button at the visible top-right. |
| 5 File preview, settings dialog, todo panel | Tests 1-2 cover the shared renderer. Manual check of each surface. |
| 6 Themes, narrow width, styling unchanged, one-line cells, vertical growth | Test 3. Manual check in light and dark at about 800px and at full width. Cell classes are not touched. |

### Validation commands (frontend surface)
- `bun run test:web`
- `bun run lint` (run `bun install` first if `@shadcn/lint` is missing)
- `bun run typecheck`
- `bun run web:build`

### Manual browser check (build/verify stage)
Use the `verify` skill, or `uv run pbi-agent web --port <p> --no-open` with a scratch session DB (see the triage reproduction). Use a session or file that contains the wide table and a small table, and check each of the following:
1. Chat assistant message: AC1, AC2, AC3 and AC4, including the copy button at `scrollLeft` > 0 for both hover and keyboard focus.
2. Workspace file preview of a `.md` file with the wide table: the table stays inside the bordered card and only the table scrolls.
3. Settings preview dialog (a skill, command or agent whose markdown has a wide table): only the table scrolls, and the dialog body does not move sideways.
4. Todo panel with a wide table in a todo item: the table scrolls (it is no longer clipped).
5. Repeat 1 in dark theme and at a narrow window width.
6. Record the measurements (`scrollWidth`/`clientWidth` of the card and wrapper) in `build.md`.

### Static bundle
`src/pbi_agent/web/static/app` **is tracked in git**. CI (`.github/workflows/tests.yml:65-68`, `release.yml:145-149`) runs `git diff --exit-code` on it after building.
- Rebuild it with `bun run web:build` using Bun 1.4.4 (the CI pin; the local version is already 1.4.4). The script runs `bun --bun vite build`. A Node-run Vite build gives different chunk hashes and the CI check fails.
- Include the regenerated `src/pbi_agent/web/static/app/**` in the change set. Leave committing to the user or release stage.

## Assumptions and defaults
- The copy overlay may briefly cover part of the last visible header cell while the table is hovered. This matches today's code-block and table behaviour and is accepted. No overlay restyle.
- The assistant card's `overflow-x-auto` is kept. Removing it is outside "layout changes beyond what is needed".
- Thinking-body and work-run tables are fixed as a side effect. No separate tests beyond the shared renderer tests.
- No docs change: this is a UI bug fix with no documented behaviour change. No Python change, so no Python checks.
- Scope: about 3 source/test files (`MarkdownContent.tsx`, `MarkdownContent.test.tsx`, `TimelineEntry.test.tsx`) plus the static bundle. Risk stays `normal` (no risk triggers; the static bundle is generated output).

plan: ready
