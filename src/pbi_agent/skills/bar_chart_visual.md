# Bar Chart Visual

Use PBIR bar-chart patterns with `Category` + `Y` roles, series-level formatting, and optional visual filters.

## Supported Visual Types

- `barChart`
- `clusteredBarChart`
- `stackedBarChart`
- `hundredPercentStackedBarChart`

## Required Query Shape

- `visual.visualType` set to one of the bar chart types.
- `visual.query.queryState.Category.projections`: at least one categorical field.
- `visual.query.queryState.Y.projections`: one or more measures.
- Optional: `visual.query.sortDefinition` for explicit sort behavior.
- Optional: `filterConfig.filters` for fixed-scope visual filtering.

## Common Object Blocks

- `valueAxis`: show/hide, axis title, display units.
- `categoryAxis`: label formatting and density control.
- `labels`: show/hide and precision.
- `dataPoint`: per-series color using `selector.metadata`.
- `legend`: position and visibility.
- `visualContainerObjects`: title/background/border/dropShadow.

## Minimal PBIR Skeleton

```json
{
  "visual": {
    "visualType": "clusteredBarChart",
    "query": {
      "queryState": {
        "Category": {
          "projections": [
            {
              "field": {
                "Column": {
                  "Expression": { "SourceRef": { "Entity": "<dimension_table>" } },
                  "Property": "<category_column>"
                }
              },
              "queryRef": "<dimension_table>.<category_column>"
            }
          ]
        },
        "Y": {
          "projections": [
            {
              "field": {
                "Measure": {
                  "Expression": { "SourceRef": { "Entity": "<measure_table>" } },
                  "Property": "<measure_1>"
                }
              },
              "queryRef": "<measure_table>.<measure_1>"
            },
            {
              "field": {
                "Measure": {
                  "Expression": { "SourceRef": { "Entity": "<measure_table>" } },
                  "Property": "<measure_2>"
                }
              },
              "queryRef": "<measure_table>.<measure_2>"
            }
          ]
        }
      }
    },
    "objects": {
      "dataPoint": [
        {
          "properties": {
            "fill": {
              "solid": {
                "color": {
                  "expr": {
                    "Literal": { "Value": "'#00AA55'" }
                  }
                }
              }
            }
          },
          "selector": { "metadata": "<measure_table>.<measure_1>" }
        }
      ]
    }
  }
}
```

## Constraints

- Keep PBIR field node casing exact (`Measure`, `Column`, `Expression`, `SourceRef`, `Property`).
- Keep `queryRef` aligned with projected fields.
- In stacked/100% stacked charts, use consistent series ordering across related pages.
- Prefer selector-scoped formatting over global formatting when multiple measures are shown.
