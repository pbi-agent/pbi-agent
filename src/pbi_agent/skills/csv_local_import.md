# Local CSV Import

Use this when creating or editing a PBIP semantic model that imports CSV data from a local file.

## Where CSV Source Is Defined In TMDL

- `definition/database.tmdl`: model compatibility only; no CSV path definition here.
- `definition/model.tmdl`: model metadata, `ref table ...` entries, and `annotation PBI_QueryOrder`.
- `definition/expressions.tmdl`: CSV path parameters with full Power BI parameter metadata.
- `definition/tables/<table>.tmdl`: real data-source logic in `partition <table> = m` with M code.
- `definition/relationships.tmdl`: relationship graph after tables are loaded.

## Domain Rules

1. In `definition/expressions.tmdl`, every CSV path parameter must be a real Power BI text parameter with `meta [IsParameterQuery = true, IsParameterQueryRequired = true, Type = "Text"]`.
2. Every parameter expression must also include a `lineageTag`, `annotation PBI_NavigationStepName = Navigation`, and `annotation PBI_ResultType = Text`.
3. In `definition/model.tmdl`, always add `annotation PBI_QueryOrder = [...]` when using CSV-backed M partitions. Put parameter expressions first, then imported tables, then `_Measures`.
4. Every imported table must have an explicit `partition <table> = m` block with `mode: import` and end with `annotation PBI_ResultType = Table`.
5. A dedicated `_Measures` table must never be left partitionless. Give it an empty import partition even if the table contains only measures.
6. Never name the measures table `Measures`; always use `_Measures`.
7. Keep all semantic model source tables on import storage semantics. Do not mix ambiguous structures that can cause Power BI to interpret the model as composite.
8. After major semantic-model surgery, delete `.pbi/cache.abf` if it exists before reopening the PBIP.

## Parameterize Local Paths

Avoid hardcoded absolute paths in `File.Contents("C:\\...")`. Create text parameters in `expressions.tmdl` and reuse them in partitions.

```tmdl
expression csv_file_path = "C:\\Data\\inbound\\sales.csv" meta [IsParameterQuery = true, IsParameterQueryRequired = true, Type = "Text"]
	lineageTag: 11111111-1111-1111-1111-111111111111

	annotation PBI_NavigationStepName = Navigation

	annotation PBI_ResultType = Text

expression csv_folder_path = "C:\\Data\\inbound" meta [IsParameterQuery = true, IsParameterQueryRequired = true, Type = "Text"]
	lineageTag: 22222222-2222-2222-2222-222222222222

	annotation PBI_NavigationStepName = Navigation

	annotation PBI_ResultType = Text
```

## Model-Level Query Order

When CSV-backed partitions are present, declare query order explicitly in `definition/model.tmdl`.

```tmdl
model Model
	culture: en-US
	defaultPowerBIDataSourceVersion: powerBI_V3
	sourceQueryCulture: en-US

annotation PBI_QueryOrder = ["csv_file_path","fact_sales","_Measures"]

ref table fact_sales
ref table _Measures
```

Keep parameters first, then imported tables, then `_Measures`.

## Single CSV File Partition Template

```tmdl
partition fact_sales = m
	mode: import
	source =
			let
			    Source = Csv.Document(
			        File.Contents(csv_file_path),
			        [Delimiter=",", Columns=4, Encoding=65001, QuoteStyle=QuoteStyle.Csv]
			    ),
			    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
			    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
			        {"order_id", Int64.Type},
			        {"order_date", type date},
			        {"amount", type number},
			        {"customer", type text}
			    })
			in
			    #"Changed Type"

annotation PBI_ResultType = Table
```

## Local Folder Partition Template

Use this when the source is a folder with many CSV files sharing the same schema.

```tmdl
partition fact_sales = m
	mode: import
	source =
			let
			    Source = Folder.Files(csv_folder_path),
			    #"Keep CSV" = Table.SelectRows(Source, each Text.Lower([Extension]) = ".csv"),
			    #"Parsed Tables" = List.Transform(#"Keep CSV"[Content], each Table.PromoteHeaders(Csv.Document(_, [Delimiter=",", Columns=4, Encoding=65001, QuoteStyle=QuoteStyle.Csv]), [PromoteAllScalars=true])),
			    #"Combined Data" = Table.Combine(#"Parsed Tables"),
			    #"Changed Type" = Table.TransformColumnTypes(#"Combined Data",{
			        {"order_id", Int64.Type},
			        {"order_date", type date},
			        {"amount", type number},
			        {"customer", type text}
			    })
			in
			    #"Changed Type"

annotation PBI_ResultType = Table
```

## Dedicated Measures Table Pattern

Never leave `_Measures` without a partition.

```tmdl
table _Measures
	measure 'Sales Amount' = SUM(fact_sales[amount])
		formatString: $#,##0.00

	partition _Measures = m
		mode: import
		source =
				let
				    Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("i44FAA==", BinaryEncoding.Base64), Compression.Deflate)), let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [Column1 = _t]),
				    #"Changed Type" = Table.TransformColumnTypes(Source, {{"Column1", type text}}),
				    #"Removed Columns" = Table.RemoveColumns(#"Changed Type", {"Column1"})
				in
				    #"Removed Columns"

	annotation PBI_ResultType = Table
```

## Column And Model Definition Rules

- Declare each model column in the table TMDL with explicit `dataType`, `summarizeBy`, and `sourceColumn`.
- Keep source-to-model names stable; report bindings rely on exact field names.
- Set `formatString` explicitly for numeric and date business fields.
- Add date variations and relationships only when date hierarchy UX is needed.

## Validation Checklist

1. Confirm delimiter, encoding, quote style, and expected column count match real files.
2. Confirm every referenced column exists after header promotion.
3. Confirm local path exists on the refresh machine, not only the developer machine.
4. Confirm model column types match `Table.TransformColumnTypes`.
5. Confirm `definition/model.tmdl` includes `annotation PBI_QueryOrder`.
6. Confirm every CSV path parameter includes `meta [...]`, `lineageTag`, `PBI_NavigationStepName`, and `PBI_ResultType = Text`.
7. Confirm all imported tables, including `_Measures`, have `partition ... = m`, `mode: import`, and `annotation PBI_ResultType = Table`.
8. Confirm relationships still validate after refresh (`relationships.tmdl` keys and datatypes).
9. Confirm `.pbi/cache.abf` is removed after major semantic-model refactors when present.

## Common Failure Modes

- Wrong delimiter or encoding: columns shift or mojibake appears.
- Header row not promoted: `sourceColumn` mapping fails.
- Hardcoded user path: refresh fails on other machines.
- Folder import with mixed schemas: expand and type steps fail on some files.
- Local path in Service without gateway: scheduled refresh fails.
- Parameter expression stops at `meta [...]` and omits `lineageTag` or Power BI annotations.
- `model.tmdl` omits `PBI_QueryOrder`, so Power BI misreads storage semantics during validation.
- `_Measures` exists as measures-only metadata with no import partition.

## Quick Recovery Recipe

If the composite-model validation error appears:

1. Fix the semantic model first; do not try to solve it in report visual JSON.
2. Add missing parameter metadata and annotations in `definition/expressions.tmdl`.
3. Add or fix `annotation PBI_QueryOrder` in `definition/model.tmdl`.
4. Add missing `mode: import` partitions and `annotation PBI_ResultType = Table`, including `_Measures`.
5. Delete `.pbi/cache.abf`.
6. Reopen the PBIP and refresh the model.
