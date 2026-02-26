# Card Visual

Use PBIR card patterns (`cardVisual` and `card`) with correct query roles and selector-scoped formatting.

## Visual Type Choice

- Use `"cardVisual"` when editing legacy/multi-tile cards.
- Use `"card"` for modern single-value cards.
- Do not switch type in-place unless you migrate the full object/query schema.

## Required Structure

- For `cardVisual`:
  - `visual.query.queryState.Data.projections`.
  - Optional multi-field tiles with `selector.metadata` formatting.
- For `card`:
  - `visual.query.queryState.Values.projections`.
  - Single primary callout value.
- Keep query expression casing exact: `Measure`/`Column`/`Expression`/`SourceRef`/`Property`.

## Common Object Blocks (`cardVisual`)

- `layout`: orientation, alignment, tile behavior.
- `label`: text, placement, font, per-field override.
- `value`: font size/color/alignment, per-field override.
- `accentBar`: status-color strip per field.
- `padding`, `spacing`, `outline`, `shapeCustomRectangle`.
- `visualContainerObjects`: `title`, `background`, `border`, `dropShadow`.

## Minimal PBIR Skeleton

```json
{
  "visual": {
    "visualType": "cardVisual",
    "query": {
      "queryState": {
        "Data": {
          "projections": [
            {
              "field": {
                "Measure": {
                  "Expression": { "SourceRef": { "Entity": "<measure_table>" } },
                  "Property": "<metric_name>"
                }
              },
              "queryRef": "<measure_table>.<metric_name>"
            }
          ]
        }
      }
    },
    "objects": {
      "label": [
        {
          "properties": {
            "text": { "expr": { "Literal": { "Value": "'<label_text>'" } } }
          },
          "selector": { "metadata": "<measure_table>.<metric_name>" }
        }
      ],
      "value": [
        {
          "properties": {
            "fontSize": { "expr": { "Literal": { "Value": "20D" } } }
          }
        }
      ]
    }
  }
}
```

## Constraints

- Preserve `selector.metadata` in multi-field cards when editing formatting.
- Keep `queryRef` and `Property` names exact, including spaces/symbols.
- Use explicit formatting for status/threshold cards instead of relying only on theme defaults.
