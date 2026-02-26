# Slicer Visual

Use `slicer` visual patterns with synced filters (`syncGroup`) and either date-range or dropdown interaction.

## Required Structure

- `visual.visualType = "slicer"`.
- Bind one field in `visual.query.queryState.Values.projections`.
- Optional `query.sortDefinition` for date fields.
- Add `syncGroup` so filters stay consistent across hidden/visible pages.
- `syncGroup.groupName` must represent one field only. Do not reuse same group name for different fields.

## Common Modes

- Date range slicer: `objects.data.properties.mode = 'Between'`, with `header.show = false`, `slider.color`.
- Dropdown slicer: `objects.data.properties.mode = 'Dropdown'`, often with `general.selfFilterEnabled = true`.

## Generic Sync Group Design

- Use stable semantic names:
  - `date_main`
  - `entity_main`
  - `system_main`
- Keep one group per field. Never mix fields in the same group.
- Use separate groups for alternate filter scopes (for example executive vs operational pages).

## Common Container Styling

- `visualContainerObjects.background.show = true`.
- `visualContainerObjects.border.show = false`.
- `visualContainerObjects.dropShadow.show = false`.
- `visualContainerObjects.visualHeader.show = false`.

## Minimal Date Slicer Skeleton

```json
{
  "visual": {
    "visualType": "slicer",
    "query": {
      "queryState": {
        "Values": {
          "projections": [
            {
              "field": {
                "Column": {
                  "Expression": { "SourceRef": { "Entity": "<date_table>" } },
                  "Property": "<date_column>"
                }
              },
              "queryRef": "<date_table>.<date_column>"
            }
          ]
        }
      }
    },
    "objects": {
      "data": [{ "properties": { "mode": { "expr": { "Literal": { "Value": "'Between'" } } } } }]
    },
    "syncGroup": {
      "groupName": "date_main",
      "fieldChanges": true,
      "filterChanges": true
    }
  }
}
```

## How To Synchronize Multiple Filters Across Pages

1. Add slicers on each participating page for the same fields (date/site/system).
2. Use identical `syncGroup.groupName` per field on every participating page.
3. Keep projection field expression identical (`Entity` + `Property`) across those pages.
4. Keep `fieldChanges: true` and `filterChanges: true`.
5. Verify by changing one slicer and confirming all pages open with same selection.
6. Do not mix legacy and new group names unless you intentionally want isolated behavior.

## Constraint

- Reuse existing `syncGroup.groupName` when editing an existing cross-page filter; creating a new group breaks synchronization.
