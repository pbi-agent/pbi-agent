# Bar Chart Visual

Properties and JSON structure for Bar and Column chart visuals in Power BI PBIR format.

## Overview

Bar charts display categorical data with horizontal bars; column charts use
vertical bars. Both share the same property structure. Use `clusteredBarChart`
for horizontal and `clusteredColumnChart` for vertical. Stacked variants are
`stackedBarChart` and `stackedColumnChart`.

## Visual Type Options

| visualType                         | Orientation | Grouping       |
| ---                                | ---         | ---            |
| `clusteredBarChart`                | Horizontal  | Side-by-side   |
| `clusteredColumnChart`             | Vertical    | Side-by-side   |
| `stackedBarChart`                  | Horizontal  | Stacked        |
| `stackedColumnChart`               | Vertical    | Stacked        |
| `hundredPercentStackedBarChart`    | Horizontal  | 100% stacked   |
| `hundredPercentStackedColumnChart` | Vertical    | 100% stacked   |

## Required Properties

| Property                                        | Type   | Description            |
| ---                                             | ---    | ---                    |
| `visual.visualType`                             | string | One of the types above |
| `visual.query.queryState.Category.projections`  | array  | Category axis field(s) |
| `visual.query.queryState.Y.projections`         | array  | Value axis measure(s)  |

## Optional Properties

| Property                                            | Type   | Description                       |
| ---                                                 | ---    | ---                               |
| `visual.query.queryState.Series.projections`        | array  | Legend / series split field       |
| `visual.objects.categoryAxis.properties.show`       | bool   | Show category axis                |
| `visual.objects.categoryAxis.properties.labelColor` | color  | Axis label color                  |
| `visual.objects.categoryAxis.properties.fontSize`   | int    | Axis label font size              |
| `visual.objects.valueAxis.properties.show`          | bool   | Show value axis                   |
| `visual.objects.valueAxis.properties.gridlineShow`  | bool   | Show gridlines                    |
| `visual.objects.valueAxis.properties.start`         | number | Axis minimum value                |
| `visual.objects.valueAxis.properties.end`           | number | Axis maximum value                |
| `visual.objects.legend.properties.show`             | bool   | Show/hide legend                  |
| `visual.objects.legend.properties.position`         | string | Top, Bottom, Left, Right          |
| `visual.objects.dataPoint.properties.fill`          | color  | Bar color (single series)         |
| `visual.objects.labels.properties.show`             | bool   | Show data labels                  |
| `visual.objects.labels.properties.color`            | color  | Data label color                  |
| `visual.objects.labels.properties.labelDisplayUnits`| int    | Label display units               |
| `visual.objects.labels.properties.labelPrecision`   | int    | Label decimal places              |

## Minimal JSON Structure

```json
{
  "visual": {
    "visualType": "clusteredColumnChart",
    "query": {
      "queryState": {
        "Category": {
          "projections": [
            {
              "field": {
                "Column": {
                  "property": "Region",
                  "expressionRef": { "source": { "entity": "Geography" } }
                }
              }
            }
          ]
        },
        "Y": {
          "projections": [
            {
              "field": {
                "measure": {
                  "property": "Total Sales",
                  "expressionRef": { "source": { "entity": "Sales" } }
                }
              }
            }
          ]
        }
      }
    },
    "objects": {
      "legend": [
        {
          "properties": {
            "show": { "expr": { "Literal": { "Value": "false" } } }
          }
        }
      ],
      "labels": [
        {
          "properties": {
            "show": { "expr": { "Literal": { "Value": "true" } } }
          }
        }
      ]
    }
  }
}
```

## Constraints

- `Category` and `Y` are both required query roles; without them the visual renders blank.
- `Series` is optional — only needed when splitting bars by a second dimension.
- Use stacked variants when showing part-to-whole relationships.
- `dataPoint.fill` applies to all bars in single-series; for multi-series, use series-scoped selectors.
