"""Prompt builder for ``pbi-agent audit`` mode."""

from __future__ import annotations

AUDIT_REPORT_FILENAME = "AUDIT-REPORT.md"


def build_audit_prompt() -> str:
    """Return the canned prompt used by audit mode.

    The assistant is instructed to inspect the current report project folder,
    evaluate it with a structured framework, and write the final markdown
    report to ``AUDIT-REPORT.md`` in the current working directory.
    """
    return f"""
Run a full Power BI report audit for the report project in the current working directory.
Do not ask the user for any additional prompt or clarification.

Use this structured analysis framework:

1) Scope and inventory
   - Identify report files, semantic model files, theme assets, and navigation elements.
   - Summarize what is present and what is missing.

2) Semantic model quality
   - Evaluate naming, table organization, measures strategy, calculated columns/tables,
     and data type consistency.
   - Flag anti-patterns (implicit measures, ambiguous naming, duplicated business logic).

3) DAX and KPI quality
   - Review measure definitions and DAX readability.
   - Check whether KPIs are explicit, reusable, and aligned with model intent.

4) Visual design and layout
   - Evaluate visual choice, information hierarchy, alignment, spacing, and consistency.
   - Check readability, labeling, and theme coherence.

5) Filtering, interactions, and navigation
   - Review slicers, sync groups, drillthrough, bookmarks, and page navigation.
   - Identify broken or confusing user flows.

6) Performance and maintainability
   - Detect likely performance risks and maintainability issues.
   - Suggest concrete optimizations.

7) Accessibility and governance
   - Assess accessibility basics (contrast, text clarity, keyboard friendliness where applicable).
   - Note documentation/readme gaps and governance concerns.

8) Prioritized remediation plan
   - Provide quick wins, medium effort improvements, and strategic improvements.

Output requirements:
- You MUST create or overwrite `{AUDIT_REPORT_FILENAME}` in the current working directory using apply_patch.
- The file MUST be detailed markdown and include:
  - Executive Summary
  - Audit Scope and Method
  - Findings by Area
  - Findings Table with columns: ID, Severity, Area, Evidence, Impact, Recommendation
  - Priority Action Plan (Now / Next / Later)
  - Confidence and Known Gaps
- Ground every finding in observed file evidence. If evidence is missing, clearly state "Not found".
- Do not invent report elements that were not observed.

After writing the file, respond briefly with confirmation and top risks.
""".strip()
