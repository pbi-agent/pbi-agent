# Navigation And Bookmarks

Use this when implementing page navigation, drillthrough actions, and bookmark-driven UX states.

## Action Button Link Types

Set in `visual.visualContainerObjects.visualLink[0].properties.type`:

- `'Back'`: return to previous page.
- `'PageNavigation'`: requires `navigationSection`.
- `'Drillthrough'`: requires `drillthroughSection`; optional `disabledTooltip`.
- `'Bookmark'`: requires `bookmark`.

## Generic Connection Rules

- Use one visible landing page and hide operational/detail pages when needed.
- Add explicit return paths to landing page (`PageNavigation`) from hidden pages.
- Use `Drillthrough` buttons for contextual jumps into details.
- Add `Back` buttons on drillthrough targets for user-friendly return flow.

## Navigator Visuals

- `pageNavigator`: control visible pages with `objects.pages[].selector.id` + `showPage`.
- `bookmarkNavigator`: switch bookmarks using:
  - `objects.bookmarks[0].properties.bookmarkGroup`
  - `objects.bookmarks[0].properties.selectedBookmark`.

## Important Validation Checks

- Never leave `navigationSection` empty (`''`) unless intentionally creating a no-op clickable asset.
- Keep `drillthroughSection` page ids stable with `pageBinding` on target page.
- For renamed pages, update both:
  - page metadata (`page.json`)
  - any link target ids in `visualLink`, `pageNavigator`, and bookmarks.

## Bookmark Files Pattern

- `definition/bookmarks/bookmarks.json`: groups and hierarchy metadata.
- `<id>.bookmark.json`: actual state snapshots.
- Use `options.targetVisualNames` for scoped updates.
- Use `explorationState.sections.<page>.visualContainers.<visual>.singleVisual.display.mode = "hidden"` for per-visual toggles.
- Use `explorationState.sections.<page>.visualContainerGroups.<groupId>.isHidden` for popup/group show-hide.
- Bookmark snapshots can include filter state; keep `suppressData: true` when bookmark is for UI state only.

## Popup Pattern

1. Create a `visualGroup` for popup elements.
2. Add open button (`type: 'Bookmark' -> show-bookmark-id`).
3. Add close button/image (`type: 'Bookmark' -> hide-bookmark-id`).
4. In show/hide bookmark files, toggle `visualContainerGroups.<group>.isHidden`.
5. Keep popup controls in `targetVisualNames` to avoid resetting unrelated visuals.

## Recommended Naming Placeholders

- Landing page id: `<home_page_id>`
- Drillthrough page id: `<detail_page_id>`
- Bookmark ids: `<bookmark_show_id>`, `<bookmark_hide_id>`, `<bookmark_state_id>`

## Constraint

- Keep bookmark ids stable once linked from buttons/navigators; changing ids breaks navigation.
