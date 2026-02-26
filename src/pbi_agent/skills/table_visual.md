# Table Visual

Use PBIR table patterns with `tableEx`, projection ordering, and robust sorting/filter behavior.

## Required Structure

- `visual.visualType` must be `"tableEx"`.
- Bind fields in `visual.query.queryState.Values.projections`.
- Use exact query casing (`Measure`/`Column`/`Expression`/`SourceRef`/`Property`).
- Optional: `query.sortDefinition` for deterministic ordering.

## Recommended Pattern

- Include stable business keys early in projection order.
- Add measures and descriptive columns after keys.
- Use explicit sort on key/date/priority metric.
- Style via:
  - `objects.columnHeaders` (`backColor`, `fontColor`)
  - `objects.grid` (`outlineColor`)
  - `visualContainerObjects` (`background`, `border`, `dropShadow`).

## Minimal PBIR Skeleton

```json
{
  "visual": {
    "visualType": "tableEx",
    "query": {
      "queryState": {
        "Values": {
          "projections": [
            {
              "field": {
                "Column": {
                  "Expression": { "SourceRef": { "Entity": "<dimension_table>" } },
                  "Property": "<key_column>"
                }
              },
              "queryRef": "<dimension_table>.<key_column>"
            },
            {
              "field": {
                "Measure": {
                  "Expression": { "SourceRef": { "Entity": "<measure_table>" } },
                  "Property": "<measure_name>"
                }
              },
              "queryRef": "<measure_table>.<measure_name>"
            }
          ]
        }
      },
      "sortDefinition": {
        "sort": [
          {
            "field": {
              "Column": {
                "Expression": { "SourceRef": { "Entity": "<dimension_table>" } },
                "Property": "<sort_column>"
              }
            },
            "direction": "Descending"
          }
        ]
      }
    }
  }
}
```

## Constraints

- Keep projection order stable; this controls visible column order.
- Do not switch to legacy `table` visual type.
- Keep sort/filter definitions aligned with projected fields.
- If used on drillthrough pages, verify required drillthrough keys are included and visible (or intentionally hidden via formatting).
