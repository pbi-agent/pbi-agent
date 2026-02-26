# Power BI TMDL Audit — Progress Tracker

> **Instructions for the agent:** Update this file after completing each step.
> Change `[ ]` to `[x]` when a step is done. Add brief notes under each step
> if needed. This file is your working checklist — keep it up to date so
> progress is never lost.

---

## Phase 1: Discovery and Inventory

- [ ] Scan project folder structure recursively
- [ ] Identify all `.tmdl` files (tables, relationships, expressions, roles, cultures)
- [ ] Identify report manifests (`.pbip`, `.pbir`, `.pbism`)
- [ ] Identify theme JSON files, images, and custom visuals
- [ ] Record model storage mode (Import / DirectQuery / Composite)
- [ ] Record compatibility level from `database.tmdl`
- [ ] Summarize inventory (table count, measure count, column count, relationship count, role count)

## Phase 2: Domain 1 — Structure and Star Schema

- [ ] STR-01: Check for missing relationships (single-table / disconnected model)
- [ ] STR-02: Check for snowflake schema (dimension-to-dimension chains)
- [ ] STR-03: Check for tables with no relationships
- [ ] STR-04: Check for wide tables (>30 columns warning, >60 critical)
- [ ] STR-05: Check for visible fact-table columns (should be hidden)

## Phase 3: Domain 2 — Modeling, Relationships and Naming

- [ ] MOD-01: Check for bidirectional cross-filtering
- [ ] MOD-02: Check for many-to-many relationships
- [ ] MOD-03: Review inactive relationships
- [ ] MOD-04: Check for text-type join columns
- [ ] MOD-05: Check for bidirectional security filtering without RLS
- [ ] MOD-06: Check object name capitalization
- [ ] MOD-07: Check for "Dim" / "Fact" prefixes in table names
- [ ] MOD-08: Check for leading/trailing whitespace in names
- [ ] MOD-09: Check for special characters in names
- [ ] MOD-10: Check for unqualified column references in DAX
- [ ] MOD-11: Check for qualified measure references in DAX
- [ ] MOD-12: Check tables with >10 visible items and no display folders
- [ ] MOD-13: Check hidden column CamelCase convention

## Phase 4: Domain 3 — Performance

- [ ] Record complexity thresholds (columns/table, total columns, tables, measures)
- [ ] PRF-01: Check calculated columns using RELATED
- [ ] PRF-02: Check calculated columns with aggregation functions
- [ ] PRF-03: Check for calculated tables
- [ ] PRF-04: Check for auto date/time tables
- [ ] PRF-05: Check date tables marked with DataCategory: Time
- [ ] PRF-06: Check DateTime columns with non-midnight values
- [ ] PRF-07: Check isAvailableInMdx on non-attribute columns
- [ ] PRF-08: Check numeric columns without summarizeBy: none
- [ ] PRF-09: Check for floating-point dataType: double
- [ ] PRF-10: Check DirectQuery model without aggregation tables

## Phase 5: Domain 4 — Security

- [ ] SEC-01: Check for hardcoded credentials in M expressions
- [ ] SEC-02: Check for local file paths in partition sources
- [ ] SEC-03: Check for hardcoded server/database names
- [ ] SEC-04: Check for PII column names without RLS
- [ ] SEC-05: Check for USERNAME() vs USERPRINCIPALNAME() in RLS
- [ ] SEC-06: Check RLS filters on fact tables
- [ ] SEC-07: Check for LOOKUPVALUE in RLS expressions
- [ ] SEC-08: Check for empty roles
- [ ] SEC-09: Check for hardcoded filter values in RLS
- [ ] SEC-10: Check for overly complex RLS expressions
- [ ] SEC-11: Check measures referencing OLS-hidden columns
- [ ] SEC-12: Check OLS combined with RLS on same table

## Phase 6: Domain 5 — DAX Quality

- [ ] DAX-01: Check FILTER on entire table inside CALCULATE
- [ ] DAX-02: Check division operator instead of DIVIDE()
- [ ] DAX-03: Check FORMAT() usage in measures
- [ ] DAX-04: Check IFERROR / ISERROR usage
- [ ] DAX-05: Check EARLIER / EARLIEST usage
- [ ] DAX-06: Check nested IF >= 4 deep
- [ ] DAX-07: Check ALL() on entire table without column specification
- [ ] DAX-08: Check COUNTROWS(VALUES()) instead of DISTINCTCOUNT
- [ ] DAX-09: Check HASONEVALUE + VALUES instead of SELECTEDVALUE
- [ ] DAX-10: Check iterator on single column instead of aggregator
- [ ] DAX-11: Check for nested iterators
- [ ] DAX-12: Check measures >200 chars with no VAR
- [ ] DAX-13: Check measure complexity thresholds
- [ ] DAX-14: Check nested CALCULATE
- [ ] DAX-15: Check measure dependency chain depth

## Phase 7: Domain 6 — Metadata and Documentation

- [ ] MET-01: Check measures without descriptions
- [ ] MET-02: Check visible columns without descriptions
- [ ] MET-03: Check tables without descriptions
- [ ] MET-04: Check descriptions that duplicate object name
- [ ] MET-05: Check descriptions shorter than 10 characters
- [ ] MET-06: Check currency measures without currency format
- [ ] MET-07: Check percentage measures without percentage format
- [ ] MET-08: Check date columns without format string
- [ ] MET-09: Check visible numeric measures without formatString
- [ ] MET-10: Check PBI_FormatHint isGeneralNumber annotation

## Phase 8: Domain 7 — Anti-Patterns and Hidden Fields

- [ ] APT-01: Check foreign key columns not hidden
- [ ] APT-02: Check Key/ID columns without summarizeBy: none
- [ ] APT-03: Check hidden columns not referenced anywhere
- [ ] APT-03b: Check unused imported columns (visible or hidden)
- [ ] APT-04: Check missing lineageTags
- [ ] APT-05: Check duplicate lineageTags
- [ ] APT-06: Check invalid lineageTag GUID format

## Phase 9: Scoring and Report Generation

- [ ] Compute per-domain pass/fail counts
- [ ] Apply category weights and compute weighted score
- [ ] Determine letter grade (A/B/C/D/F)
- [ ] Write Executive Summary to AUDIT-REPORT.md
- [ ] Write Audit Scope and Inventory section
- [ ] Write Score Card table
- [ ] Write Findings by Domain section
- [ ] Write Consolidated Findings Table
- [ ] Write Priority Action Plan (Now / Next / Later)
- [ ] Write Confidence and Known Gaps section
- [ ] Final review: confirm AUDIT-REPORT.md is complete
