# Report Structure

Use this to create or refactor PBIR report architecture (`report.json`, `pages/*.json`, visual containers) for any domain.

## Core Layout Pattern

- Canvas: `1280 x 720`, `displayOption: "FitToPage"` on all pages.
- Main entry page visible (for example `<home_page_id>`).
- Most analytic/detail pages can be hidden in app mode: `"visibility": "HiddenInViewMode"`.
- Page backgrounds use `ResourcePackageItem` images from `RegisteredResources`.
- Page order is centralized in `definition/pages/pages.json`.

## Generic Page Connection Graph

- Landing page routes to analysis pages via navigator/buttons.
- Hidden analysis/detail pages include explicit `PageNavigation` back to landing page.
- Drillthrough chain:
  - Analysis pages -> detail list pages.
  - Detail list pages -> canonical detail page via `Drillthrough` action button.
- A `Back` action button is also present on each drillthrough/detail page.

## Filter Stack And Propagation Order

1. Semantic model relationships (`relationships.tmdl`) define propagation paths.
2. Page-level filters in `page.json -> filterConfig.filters`.
3. Slicer state (including synced slicers via `syncGroup`).
4. Visual-level filters in `visual.json -> filterConfig.filters`.
5. Drillthrough parameter binding in `pageBinding`.
6. Bookmark restore/hide state (can change visible visuals and filter snapshot).

## Drillthrough Binding Pattern

- In target page `page.json`, declare one or more drillthrough filters:
  - `filterConfig.filters[*].howCreated = "Drillthrough"`.
- Bind each with `pageBinding.parameters`:
  - `boundFilter` references filter id in same file.
  - `fieldExpr` must exactly match source field expression.
- Common patterns:
  - Single key drillthrough (`<dimension>.<key>`).
  - Composite key drillthrough (`<key1>`, `<key2>`, `<key3>`).
  - KPI/value drillthrough (`<measure_table>.<measure_name>`).

## Generic Multi-Page Synced Filter Strategy

- Create one sync group per shared field:
  - `date_main` -> `<date_table>.<date_column>`
  - `entity_main` -> `<entity_table>.<entity_column>`
  - `system_main` -> `<system_table>.<system_column>`
- Reuse the same group name only for the same field on all participating pages.
- Use different group names when intentionally isolating legacy or alternate behavior.

## Visual Grouping Pattern

- Use `visualGroup` containers for zones (header, popup, detail block).
- Child visuals set `parentGroupName`.
- Use bookmarks to toggle `visualContainerGroups.<groupId>.isHidden` for full popup open/close behavior.

## One-Shot Build Order

1. Create pages + order + backgrounds.
2. Create navigators and page return links.
3. Create slicers with stable `syncGroup` names before charts.
4. Add visuals and per-visual filters.
5. Add drillthrough target pages with `filterConfig` + `pageBinding`.
6. Add drillthrough and back buttons.
7. Add bookmarks for popup/filter mode toggles.
