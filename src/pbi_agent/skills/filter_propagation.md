# Filter Propagation

Use this when wiring page-to-page filtering behavior (slicers, drillthrough, page filters, visual filters).

## Propagation Model

1. Model relationships propagate filter context across tables.
2. Page-level filters (`page.json -> filterConfig`) apply to all visuals on page.
3. Synced slicers (`syncGroup`) share user selections across pages in same group.
4. Visual filters (`visual.json -> filterConfig`) add local constraints.
5. Drillthrough binding (`pageBinding`) injects source context into target page filters.
6. Bookmarks can restore/snapshot visual/filter state.

## Generic Filter Topology (Recommended)

- Global analytical pages:
  - `date` slicer sync group (for example `date_main`).
  - `entity/site` slicer sync group (for example `site_main`).
  - `system/channel` slicer sync group (for example `system_main`).
- Detail pages:
  - drillthrough filters for one key or multiple keys.
  - optional extra user slicers scoped to details only.

## Drillthrough Context Pattern

- Source visual/button:
  - `visualLink.type = 'Drillthrough'`
  - `drillthroughSection = '<target_page_id>'`
- Target page:
  - `filterConfig.filters[*].howCreated = "Drillthrough"`
  - `pageBinding.type = "Drillthrough"`
  - `pageBinding.parameters[*].boundFilter` mapped to `fieldExpr`.
- Result: selected source context is injected into target filters.

## Implementation Rules

- For synced slicers:
  - same field expression
  - same `syncGroup.groupName`
  - `fieldChanges = true`, `filterChanges = true`.
- For drillthrough:
  - keep `boundFilter` id valid and local to target page.
  - keep `fieldExpr` identical to bound filter field.
- For fixed-scope visuals:
  - use visual-level categorical filters in `visual.json -> filterConfig`.

## Validation Checklist

1. Change a synced slicer on page A, open page B, verify same selection.
2. Trigger drillthrough from multiple visuals and verify same target filter behavior.
3. Verify bookmarks used for UI state do not unintentionally reset core slicer filters.
4. Verify relationship direction/cardinality supports intended propagation path.

## Failure Modes

- New slicer with wrong group name: filter does not sync.
- Same group name with different field: undefined behavior/inconsistent filter.
- Measure/column rename in model without JSON update: visuals and drillthrough bindings break.
