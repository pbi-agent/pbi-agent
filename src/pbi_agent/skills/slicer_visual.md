# Slicer Visual

Use `slicer` visual patterns with synced filters (`syncGroup`), clear container styling, and either date-range or dropdown interaction.

## Required Structure

- `visual.visualType = "slicer"`.
- Bind one field in `visual.query.queryState.Values.projections`.
- Optional `query.sortDefinition` for date fields.
- Add `syncGroup` so filters stay consistent across hidden/visible pages.
- `syncGroup.groupName` must represent one field only. Do not reuse same group name for different fields.
- Use either `objects.header` or `visualContainerObjects.title` for slicer labeling, but not both in the same visual.

## Common Modes

- Date range slicer: `objects.data.properties.mode = 'Between'`.
- Dropdown slicer: `objects.data.properties.mode = 'Dropdown'`.
- For dropdown interaction pages, use `objects.general.properties.selfFilterEnabled = true` when self-filtering is required.

## Default Styling Pattern if no instructions given

- Header and mode:
  - `objects.header.show = false` in most pages for a cleaner filter row.
  - If a visible label is needed, enable either header or title, never both.
  - Date slicers use `mode = 'Between'`.
  - Entity/system slicers use `mode = 'Dropdown'`.
- Date slider color:
  - `objects.slider.color` uses brand accent (`'#B6975A'`) in Between mode.
- Container style baseline:
  - `visualContainerObjects.background.show = true`
  - `visualContainerObjects.background.transparency = 0D` (or `50D` for lighter overlays)
  - `visualContainerObjects.border.radius = 5D`
  - `visualContainerObjects.border.width = 1D` (sometimes `2D` on framed pages)
  - Keep `border.show = false` by default; enable for dedicated filter panels.
  - Keep `dropShadow.show = false` by default; enable only when slicer must read as a floating filter card.
- Sync groups examples:
  - Date groups: `date_id`, `date_id1`, `date_id2`
  - Entity groups: `category_name`, `product_type`, etc.

## UX/UI Guidance

- Keep filter order stable across pages (typically date, then site, then system).
- Keep slicer size/position consistent so users build muscle memory.
- Use one sync group per field and reuse it globally to avoid filter drift.
- Avoid duplicate labeling chrome: choose header or title based on layout needs, and disable the other.
- For Between slicers, optional `startDate`/`endDate` can set intentional default windows.
- For long dropdown lists, keep slicer width sufficient and prefer searchable dropdown behavior.
- Use this size by default to prevent cropping: "height": 88, "width": 228.

## Minimal Date Slicer Skeleton

```json
{
  "$schema": "visual_container_schema_skill",
  "name": "88888888888888888888",
  "position": {
    "x": 350,
    "y": 115,
    "z": 7000,
    "height": 70,
    "width": 220
  },
  "visual": {
    "visualType": "slicer",
    "query": {
      "queryState": {
        "Values": {
          "projections": [
            {
              "field": {
                "Column": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "TableName"
                    }
                  },
                  "Property": "ColumnName"
                }
              },
              "queryRef": "TableName.ColumnName",
              "nativeQueryRef": "ColumnName",
              "active": true
            }
          ]
        }
      }
    },
    "objects": {
      "data": [
        {
          "properties": {
            "mode": {
              "expr": {
                "Literal": {
                  "Value": "'Dropdown'"
                }
              }
            }
          }
        }
      ],
      "general": [
        {
          "properties": {
            "selfFilterEnabled": {
              "expr": {
                "Literal": {
                  "Value": "true"
                }
              }
            }
          }
        }
      ],
      "header": [
        {
          "properties": {
            "show": {
              "expr": {
                "Literal": {
                  "Value": "true"
                }
              }
            },
            "text": {
              "expr": {
                "Literal": {
                  "Value": "'Friendly Column Name'"
                }
              }
            }
          }
        }
      ]
    },
    "visualContainerObjects": {
      "background": [
        {
          "properties": {
            "show": {
              "expr": {
                "Literal": {
                  "Value": "true"
                }
              }
            },
            "transparency": {
              "expr": {
                "Literal": {
                  "Value": "0D"
                }
              }
            }
          }
        }
      ],
      "border": [
        {
          "properties": {
            "show": {
              "expr": {
                "Literal": {
                  "Value": "true"
                }
              }
            },
            "radius": {
              "expr": {
                "Literal": {
                  "Value": "6D"
                }
              }
            },
            "width": {
              "expr": {
                "Literal": {
                  "Value": "1D"
                }
              }
            },
            "color": {
              "solid": {
                "color": {
                  "expr": {
                    "Literal": {
                      "Value": "'#C9D4E5'"
                    }
                  }
                }
              }
            }
          }
        }
      ],
      "title": [
        {
          "properties": {
            "show": {
              "expr": {
                "Literal": {
                  "Value": "false"
                }
              }
            }
          }
        }
      ]
    },
    "syncGroup": {
      "groupName": "sg_column_name",
      "fieldChanges": true,
      "filterChanges": true
    },
    "drillFilterOtherVisuals": true
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
