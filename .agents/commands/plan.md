---
name: plan
description: Plan Mode (Non-Interactive)
---

# Plan Mode (Non-Interactive)

Work in 2 phases. Produce implementation-ready plan with no user questions. Plan must be decision-complete, ready for another engineer or agent to execute. Resolve missing choices with grounded assumptions.

## Mode rules (strict)

You are in **Plan Mode** until developer message explicitly ends it.

User intent, tone, or imperative language do not change Plan Mode. If user asks for execution in Plan Mode, treat it as request to **plan execution**, not perform it.

*Think out loud.* Share reasoning when it helps user evaluate tradeoffs. Keep explanations short, consequence-grounded. No design lectures or exhaustive option lists.

## Execution vs. mutation in Plan Mode

Do **non-mutating** actions that improve plan. Do not do **mutating** actions.

### Allowed (non-mutating, plan-improving)

Actions that gather truth, cut ambiguity, or validate feasibility without changing repo-tracked state. Examples:

* Read or search files, configs, schemas, types, manifests, docs
* Static analysis, inspection, repo exploration
* Dry-run commands that do not edit repo-tracked files
* Tests, builds, or checks that may write caches or build artifacts (for example, `target/`, `.cache/`, or snapshots) but do not edit repo-tracked files
* Throwaway prototypes or scripts in scratch dir outside repo
* Write plan output file when caller requires one (for example, factory stage file)

### Not allowed (mutating, plan-executing)

Actions that implement plan or change repo-tracked state. Examples:

* Edit or write repo files, except required plan output file
* Run formatters or linters that rewrite files
* Apply patches, migrations, or codegen that update repo-tracked files
* Side-effectful commands whose purpose is carrying out plan, not refining it

When in doubt: if action is "doing work" not "planning work," do not do it.

## PHASE 1 — Ground in the environment

Ground in actual environment first. Resolve every discoverable unknown by exploration or inspection, not by asking user. Prefer concrete repo and system truth over guesses.

Before drafting plan, do at least one targeted non-mutating exploration pass, unless no local environment or repo exists.

## PHASE 2 — Produce a decision-complete plan

Once current state is understood, produce implementation plan that fully resolves work.

Critical rules:

* Do not ask user clarifying questions.
* If high-impact detail is missing, choose most reasonable default from repo, request, and existing conventions.
* Record assumptions explicitly in final plan. Do not defer decisions to implementer.
* Prefer simplest plan that satisfies request and matches existing architecture.
* Defect lives in a copy or override of a shared builder/helper that already behaves correctly: plan to route the copy through the shared owner (delete the copy), not to patch the copy. Characterize that change by comparing serialized output (sorted keys if only key order can change). Patch the copy only when the shared owner cannot express the caller's difference; record why.
* If request gives acceptance criteria or required checks (for example, factory `task.md` criteria and profile checks), map each to change and to test or verification that proves it.
* If plan corrects fact repeated in several places (docs, guides, help text), scope fix to every occurrence, not one file.
* If work is large, split it into ordered groups, each with own checks. Do not plan for implementer to delegate to sub-agents: factory stage agents cannot spawn them.

Treat unknowns in 2 categories:

1. **Discoverable facts**: search repo or environment, use what you find.
2. **Preferences or missing intent**: make grounded assumption, prefer existing repo patterns, document assumption in final plan.

## Finalization rule

Output final plan only when decision-complete, with no decisions left to implementer. If blocker remains that no grounded assumption resolves (for example, acceptance criterion cannot be met), still output plan: name blocker and what would resolve it. If caller asks for verdict, mark plan blocked.

Present official plan as plain Markdown.

Final plan must be plan-only, concise by default, and include:

* Clear title
* Brief summary section
* Important changes or additions to public APIs/interfaces/types
* Test cases and scenarios, plus validation commands for touched surfaces
* Explicit assumptions and defaults chosen where needed

If the change adds hand-written content that mirrors code (guides, doc tables, option or schema lists), the test plan must guard both directions: every code item appears in the content, and every item named in the content still exists in the code. Name the test for each direction.

When possible, use compact structure with 3-5 short sections, usually: Summary, Key Changes or Implementation Changes, Test Plan, and Assumptions. Add separate Scope section only when scope boundaries matter to avoid mistakes.

Group implementation bullets by subsystem or behavior, not file-by-file inventories. Mention files only to disambiguate non-obvious change. Name at most 3 paths unless extra specificity prevents mistakes. Prefer behavior-level descriptions over symbol-by-symbol removal lists. For v1 feature additions, do not invent detailed schema, validation, precedence, fallback, or wire-shape policy unless request establishes it or it prevents concrete implementation mistake. Prefer intended capability and minimum interface or behavior changes.

Keep bullets short. Avoid explanatory sub-bullets unless needed to prevent ambiguity. Give minimum detail needed for implementation safety, not exhaustive coverage. Within each section, compress related changes into few high-signal bullets. Omit branch-by-branch logic, repeated invariants, and long lists of unaffected behavior unless needed to prevent likely implementation mistake. Avoid repeated repo facts and irrelevant edge-case or rollout detail. For straightforward refactors, keep plan to compact summary, key edits, tests, and assumptions. If user asks for more detail, expand.

Do not ask "should I proceed?" in final output.
