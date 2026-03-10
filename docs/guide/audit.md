---
title: 'Audit System'
description: 'How pbi-agent audit scores a PBIP project and what files it writes.'
layout: doc
outline: [2, 3]
---

# Audit System

`pbi-agent audit` runs a resumable best-practice audit against the local PBIP project directory and writes markdown output into that directory.

::: warning
Audit mode evaluates the local project files only. It intentionally ignores Power BI Service settings such as workspace configuration, gateways, deployment pipelines, and dataflows.
:::

## Audit Domains

| Domain | Weight | Focus |
| --- | --- | --- |
| Security | `x3.0` | Credentials, PII exposure, RLS/OLS design, and risky data access patterns |
| Performance | `x1.5` | Model size, calculated objects, data types, and query efficiency |
| DAX Quality | `x1.5` | Common DAX anti-patterns, complexity, and maintainability |
| Modeling | `x1.5` | Relationships, naming, join columns, and display organization |
| Structure | `x1.5` | Star schema shape, disconnected tables, and exposed fact fields |
| Documentation | `x1.0` | Descriptions, formatting metadata, and semantic clarity |
| Anti-patterns | `x1.0` | Hidden-field hygiene, unused columns, and lineage tag problems |

## Severity Scale

| Severity | Meaning |
| --- | --- |
| `1` | Cosmetic or informational |
| `2` | Minor warning |
| `3` | Important issue with functional or performance impact |
| `4` | High-risk issue |
| `5` | Critical issue |

## Letter Grades

| Grade | Score Range | Interpretation |
| --- | --- | --- |
| `A` | `90-100%` | Production-ready |
| `B` | `80-89%` | Minor improvements needed |
| `C` | `70-79%` | Several issues to address |
| `D` | `60-69%` | Significant improvements needed |
| `F` | `<60%` | Critical issues present |

## Output Files

| File | Purpose |
| --- | --- |
| `AUDIT-REPORT.md` | Incrementally written audit report with findings, score card, and action plan |
| `AUDIT-TODO.md` | Progress checklist used to support long-running audits and resume behavior |

```bash
uv run pbi-agent audit --report-dir .
```

::: details Resume behavior
At startup, the audit workflow reads `AUDIT-TODO.md` and any existing `AUDIT-REPORT.md`. Completed checklist items are skipped, and the run resumes from the first unchecked phase or rule instead of starting over.
:::

::: tip
The score is weighted by domain, not just by raw finding count, so a small number of security failures can affect the final grade more than several documentation issues.
:::
