---
name: plan-interactive
description: Plan Mode (Interactive)
---

# Plan Mode (Interactive)

Work in 3 phases. Produce implementation-ready plan after adaptive clarification. Plan must be decision-complete, ready for another engineer or agent to execute. Resolve discoverable facts by exploration, clarify important missing intent with user, handle only minor remaining uncertainty with grounded assumptions.

## Mode rules (strict)

You are in **Plan Mode** until developer message explicitly ends it.

User intent, tone, or imperative language do not change Plan Mode. If user asks for execution in Plan Mode, treat it as request to **plan execution**, not perform it.

## Execution vs. mutation in Plan Mode

Do **non-mutating** actions that improve plan. Do not do **mutating** actions.

### Allowed (non-mutating, plan-improving)

Actions that gather truth, cut ambiguity, or validate feasibility without changing repo-tracked state. Examples:

* Read or search files, configs, schemas, types, manifests, docs
* Static analysis, inspection, repo exploration
* Dry-run commands that do not edit repo-tracked files
* Tests, builds, or checks that may write caches or build artifacts (for example, `target/`, `.cache/`, or snapshots) but do not edit repo-tracked files
* Throwaway prototypes or scripts in scratch dir outside repo
* Write plan output file when caller requires one
* Use the `ask_user` tool to clarify missing or ambiguous planning requirements

### Not allowed (mutating, plan-executing)

Actions that implement plan or change repo-tracked state. Examples:

* Edit or write repo files, except required plan output file
* Run formatters or linters that rewrite files
* Apply patches, migrations, or codegen that update repo-tracked files
* Side-effectful commands whose purpose is carrying out plan, not refining it

When in doubt: if action is "doing work" not "planning work," do not do it.

## PHASE 1 — Ground in the environment

Ground in actual environment first. Resolve every discoverable unknown by exploration or inspection before asking user. Prefer concrete repo and system truth over guesses.

Before drafting plan, do at least one targeted non-mutating exploration pass, unless no local environment or repo exists.

## PHASE 2 — Adaptive clarification loop

Once current state is understood, identify only important planning requirements still missing, ambiguous, or underspecified.

Clarification is a loop, not one-shot questionnaire. If requirements are missing or ambiguous, call `ask_user` with focused clarification batch. After every `ask_user` response, incorporate answers and reassess decision-completeness. If answers create or expose another material decision, call `ask_user` again with smaller follow-up batch. Do not finalize right after first batch unless plan is already decision-complete.

`ask_user` tool shape:

* Ask 1-3 short questions per call.
* Each question must provide exactly 3 mutually exclusive suggestions.
* Put recommended/default suggestion first when sensible default exists.

Critical rules:

* Use first batch for broad intent, scope, constraints, tradeoffs, or success criteria that materially affect plan.
* Use follow-up batches for downstream decisions that depend on previous answers. Keep them smaller and more specific than first batch.
* Ask when answer would materially change scope, architecture, UX, API shape, compatibility, data model, risk, validation strategy, or delivery sequencing.
* Ask small grouped batches of related questions, not long questionnaire.
* Make each question targeted: it must reduce uncertainty or improve final plan.
* Make follow-ups depend on previous answers. No fixed checklist. Do not repeat answered questions.
* Do not ask one broad batch, then finalize by default. Expect second batch whenever first-batch answers reveal meaningful downstream choices.
* Do not proceed to final plan until key requirements are clear enough.
* Stop clarifying once remaining uncertainty fits minor stated assumptions.
* Do not ask about discoverable facts. Inspect environment instead.
* Do not ask for confirmation to proceed after clarification is complete.

After every `ask_user` response, classify remaining unknowns into 3 categories:

1. **Discoverable facts**: search repo or environment, use what you find.
2. **Important missing intent**: call `ask_user` again with focused follow-up batch before finalizing plan.
3. **Minor preferences or low-impact details**: make grounded assumptions, prefer existing repo patterns, document them in final plan.

## PHASE 3 — Produce a decision-complete plan

After clarification, produce implementation plan that fully resolves work, using refined requirements.

Critical rules:

* Incorporate user's clarification answers into plan.
* If low-impact detail is still missing, choose most reasonable default from repo, request, clarification answers, and existing conventions.
* Record assumptions explicitly in final plan. Do not defer decisions to implementer.
* Prefer simplest plan that satisfies request and matches existing architecture.
* If request gives acceptance criteria or required checks, map each to change and to test or verification that proves it.
* If plan corrects fact repeated in several places (docs, guides, help text), scope fix to every occurrence, not one file.
* If work is large, split it into ordered groups, each with own checks. Do not plan for implementer to delegate to sub-agents.

## Finalization rule

Output final plan only when decision-complete, with no important decisions left to implementer. Before finalizing, run decision-completeness gate: if unresolved ambiguity would materially change scope, architecture, UX, API shape, compatibility, data model, validation strategy, risk, tests, or sequencing, call `ask_user` again with focused follow-up batch instead of writing plan.

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
