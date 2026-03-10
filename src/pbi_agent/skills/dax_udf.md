# DAX User-Defined Functions

Use this when creating, editing, or reviewing DAX user-defined functions (UDFs) in Power BI semantic models, DAX query scripts, or `functions.tmdl`.

## Scope

Apply this skill when the task involves reusable DAX logic that should live as a model function instead of being duplicated across measures, calculated columns, or visual calculations.

Use a UDF when:
- The same business rule appears in multiple measures or columns.
- The model needs shared helper logic with controlled parameter types.
- A PBIP/TMDL project includes or should include `definition/functions.tmdl`.

Do not use a UDF when:
- The logic is one-off and local to a single measure.
- The design depends on recursion, overloads, optional parameters, or explicit return types.
- The model has no tables.

## Hard Rules

1. Treat UDFs as preview-only model objects. Preserve existing UDF syntax exactly and avoid introducing unsupported patterns.
2. When editing PBIP/TMDL projects, place model-level UDFs in `definition/functions.tmdl`.
3. In DAX query scripts, use:

```dax
DEFINE
    FUNCTION <Name> = ( <params> ) => <body>
```

4. In TMDL scripts, use:

```tmdl
createOrReplace
    function <Name> = ( <params> ) => <body>
```

5. Function names must be unique in the model.
6. Function names may use letters, digits, underscores, and periods for namespacing. Do not use spaces, leading/trailing periods, consecutive periods, reserved words, or built-in DAX function names.
7. Parameter names may use only letters, digits, and underscores. Do not use periods or reserved words.
8. If you add a description, use `///` immediately above the function declaration. Do not substitute `//` or `/* */`.
9. Keep UDF bodies deterministic and readable. Prefer small composable helpers over large monolithic functions.
10. Do not assume object renames propagate into UDF bodies. If a referenced table, column, or measure is renamed, update function text manually.

## Parameter Semantics

Default parameter behavior is `AnyVal val`.

Use these rules when choosing parameter hints:

1. Use `AnyVal` for simple scalar-or-table inputs when strict typing is unnecessary.
2. Use `Scalar` or a scalar subtype when the function should accept a scalar only.
3. Use `Table` for table inputs.
4. Use `AnyRef expr` for references such as columns, measures, tables, or calendars that must be evaluated in the function context.
5. Use `val` for eager evaluation in caller context.
6. Use `expr` for lazy evaluation when the function must control filter or row context internally.
7. Remember that `expr` parameters are evaluated when referenced in the function body, not when the function is called.

Supported scalar subtypes:
- `Variant`
- `Int64`
- `Decimal`
- `Double`
- `String`
- `DateTime`
- `Boolean`
- `Numeric`

## Safe Patterns

### Small reusable scalar helper

```dax
DEFINE
    /// Add tax to an amount
    FUNCTION AddTax =
        ( amount: NUMERIC ) =>
            amount * 1.1
```

Use this pattern for shared arithmetic or normalization logic reused by multiple measures.

### Nested function composition

```dax
DEFINE
    FUNCTION AddTax =
        ( amount: NUMERIC ) =>
            amount * 1.1

    FUNCTION AddTaxAndDiscount =
        ( amount: NUMERIC, discount: NUMERIC ) =>
            AddTax(amount - discount)
```

Prefer composition over duplicating logic across functions.

### Type-checked flexible input

```dax
DEFINE
    FUNCTION StringLength =
        ( s ) =>
            IF(ISSTRING(s), LEN(s), BLANK())
```

Use runtime checks like `ISSTRING`, `ISINT64`, `ISDECIMAL`, `ISBOOLEAN`, `ISDATETIME`, `ISNUMBER`, and `ISNUMERIC` when a function intentionally accepts multiple input shapes.

### Context-sensitive table parameter

```dax
DEFINE
    FUNCTION CountRowsLater =
        ( t: TABLE EXPR ) =>
            COUNTROWS(CALCULATETABLE(t, ALL('Date')))
```

Use `TABLE EXPR` only when the function must reevaluate the table under a modified context. If the caller should materialize the table first, use `TABLE VAL` instead.

### Explicit type stabilization for calculated columns

```dax
Sales Amount with Tax =
    CONVERT(AddTax('Sales'[Sales Amount]), CURRENCY)
```

When generating calculated columns that call a UDF, force the result type if model stability depends on it.

## Editing Guidance For Agents

1. If the repo is PBIP-based, inspect `definition/functions.tmdl` before adding duplicate helper logic elsewhere.
2. If a measure repeats a business rule already implemented by a UDF, prefer calling the existing UDF instead of cloning the expression.
3. If the task asks for reusable model logic and `functions.tmdl` does not exist, add it only if the project structure clearly supports model-level functions.
4. When patching existing UDFs, preserve naming, indentation, and `///` descriptions unless the task explicitly changes them.
5. If a UDF is used by a calculated column, preserve scalar return stability and explicit conversions.
6. If a UDF is used in visual calculations, do not introduce references to model objects not present in the visual.
7. When modifying TMDL, keep syntax minimal and exact. Avoid introducing unrelated formatting churn.

## Inspection

To inspect model UDFs from DAX, use:

```dax
EVALUATE INFO.FUNCTIONS("ORIGIN", "2")
```

Use this when verifying that a function exists in the model or when auditing names and descriptions.

## Anti-Patterns

- Do not generate recursive or mutually recursive UDFs.
- Do not generate overloaded functions with the same name.
- Do not add optional parameters.
- Do not declare explicit return types.
- Do not assume Object-Level Security on referenced measures or columns automatically secures the wrapper function.
- Do not expose sensitive secured-object names casually in function names or descriptions.
- Do not assume IntelliSense support exists for every UDF editing surface.
- Do not rely on automatic rename propagation for referenced model objects.
- Do not return enum-style values for built-in APIs that require literal enum arguments.

## Constraints

- UDFs are preview features and have incomplete tooling support.
- UDFs cannot be authored or modeled in Power BI Service.
- UDFs cannot use display folders, translations, or hide/unhide workflows reliably.
- Unbound `expr` parameters are not evaluated.
- Advanced `expr` reference scenarios can produce parser inconsistencies; keep generated patterns simple and validate references carefully.
