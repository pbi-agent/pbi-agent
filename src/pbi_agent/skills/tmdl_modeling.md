# TMDL Modeling

Use this when creating or editing semantic model files (`*.tmdl`) in Power BI PBIP projects.

## Model File Layout

- `definition/database.tmdl`: database compatibility level and root database metadata.
- `definition/model.tmdl`: model metadata + table refs + culture refs.
- `definition/expressions.tmdl`: shared M parameters (for example environment/data source parameter).
- `definition/relationships.tmdl`: all relationships declared centrally.
- `definition/tables/*.tmdl`: one table per file (columns, measures, partition).
- `definition/cultures/<culture>.tmdl`: linguistic metadata.

## Recommended Conventions

- Use tab-indented TMDL blocks.
- Keep dedicated measure tables (zero columns, measures only) when model size grows.
- Use parameterized M source code in partitions for environment portability.
- Set `formatString`, `summarizeBy`, and `dataType` explicitly on business columns/measures.
- Use `variation Variation` on date columns when date hierarchy experience is required.
- Keep relationships explicit in `relationships.tmdl`.

## TMDL Syntax Cheat Sheet (Use This Exactly)

- Root object declaration:
  - `model Model`
  - `database`
  - `table <name>`
  - `relationship <id>`
  - `expression <name> = <value>`
- Nested properties use one-tab indent:
  - `dataType: int64`
  - `formatString: 0`
  - `summarizeBy: none`
- Flags are bare keywords (no `: true`):
  - `isHidden`
  - `isPrivate`
  - `isDefault`
- DAX column:
  - `column <calc_column> = <DAX expression>`
- DAX measure:
  - `measure '<metric_name>' = <DAX expression>`
- Source column mapping:
  - `sourceColumn: <source_column_name>`
- Relationship declaration:
  - `fromColumn: <from_table>.<from_column>`
  - `toColumn: <to_table>.<to_column>`
- Partition block:
  - `partition <table_name> = m`
  - `mode: import`
  - `source = <M code>`
- Annotation:
  - `annotation PBI_ResultType = Table`

## Minimal Table Template

```tmdl
table dim_example
	lineageTag: <guid>

	column key_id
		dataType: string
		summarizeBy: none
		sourceColumn: key_id

	measure '# Rows' = COUNTROWS(dim_example)
		formatString: 0

	partition dim_example = m
		mode: import
		source =
				let
				    Source = Value.NativeQuery(
				        <connector_call_using_parameter>,
				        "SELECT key_id FROM <schema_or_dataset>.dim_example_view",
				        null,
				        [EnableFolding=true]
				    )
				in
				    Source
```

## Date Variation Template

```tmdl
column asn_creation_date
	dataType: dateTime
	formatString: Short Date
	summarizeBy: none
	sourceColumn: <date_column>

	variation Variation
		isDefault
		relationship: <relationship-id>
		defaultHierarchy: LocalDateTable_<guid>.'Date Hierarchy'
```

## Common TMDL Mistakes To Avoid

- Do not convert tabs to spaces in nested blocks.
- Do not change object names casually (`queryRef`, filters, page bindings depend on them).
- Do not remove `lineageTag` for existing objects unless you intentionally recreate metadata.
- Do not change field case or rename measures used in visual JSON without updating all report references.
- Keep `fromColumn` and `toColumn` at model column names, not display names.

## Partition Template (Import)

```tmdl
partition <table_name> = m
	mode: import
	source =
			let
			    Source = Value.NativeQuery(
			        <connector_call_using_parameter>,
			        "SELECT ... FROM <schema_or_dataset>.<view_or_table>",
			        null,
			        [EnableFolding=true]
			    )
			in
			    Source
```

## Relationship Template

```tmdl
relationship <id>
	fromColumn: <from_table>.<from_column>
	toColumn: <to_table>.<to_column>
```

## Checklist Before Save

- Keep names stable (`queryRef` and report bindings depend on exact names).
- Keep `lineageTag` entries when editing existing objects.
- Keep `summarizeBy` explicit on business columns.
- Keep drillthrough/filter fields unchanged unless report bindings are updated too.
