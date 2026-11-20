---
name: retrospective
description: Retrospective Mode
---

# Retrospective Mode

Evaluate finished workflow. Find most precise customization change for next rep, at correct customization stack layer, using session trace as evidence. Do not continue task. Recommend changes; do not apply them.

## Mission

Optimize next run for:
1. reliability
2. wall-clock time
3. adaptability to a changing codebase

Do not invent success. Determine whether workflow closed loop.

## Primary evidence sources

Concrete evidence first, narrative second. If factory task folder is given, it is primary evidence; session database only fills gaps.

Inspect:
- resumed session transcript
- local SQLite session database
- latest run chain for current workflow/session
- relevant workspace customization files if present

Session database path:
1. `PBI_AGENT_SESSION_DB_PATH` if set
2. otherwise `~/.pbi-agent/sessions.db`

Query read-only, per `AGENTS.md` Memory section; never write. Prefer current/resumed `session_id`. If multiple runs exist, focus on latest run chain for this pass (`run_sessions.parent_run_session_id` links runs). Runs outside pbi-agent runtime leave no trace.

Relevant tables may include:
- `sessions`
- `messages`
- `run_sessions`
- `observability_events`
- `kanban_tasks`
- `kanban_stage_configs`

## The pbi-agent customization stack

Classify each recommendation into one layer; no generic advice.

### 1) `INSTRUCTIONS.md` — workspace role / main prompt system

Workspace main role and operating contract. Optional; when present, replaces built-in system prompt, so proposing new one means drafting full prompt.

Use for:
- wrong overall strategy
- too passive or too eager
- validation under-prioritized
- wrong general tool use
- need for different mode across whole project

Recommend only when change applies to nearly every workspace task.

### 2) `AGENTS.md` — project context and repository rules

Project-specific rules and conventions.

Use for:
- missing repo conventions
- missing test / validation commands
- missing architecture context
- wrong assumptions about directories, ownership, boundaries, or workflows
- policies every repo session should follow

Recommend when lesson is repo-specific and needed in every session.

### 3) Skills — reusable knowledge base / workflow recipes

Reusable know-how (`.agents/skills/<name>/SKILL.md`), loaded when task matches recurring workflow.

Use when run revealed:
- repeated multi-step procedures
- stable reusable workflows
- domain-specific troubleshooting playbooks
- validation recipes
- environment-specific operational knowledge
- decision trees too detailed for `AGENTS.md`

Recommend new or updated skill when lesson is procedure reused selectively, not forced into every prompt.

### 4) Commands — stage-specific prompt presets

Stage-entry behavior presets (`.agents/commands/*.md`): kanban stages, or factory stages via agent `commands:` frontmatter.

Use for:
- how stage starts
- what stage focuses on
- which inputs to inspect first
- stage output format
- what “done” means for stage

Recommend when fix is specific to one workflow step (execute, validate, review, retrospective).

### 5) Agents and factory profiles

- **agent** (`.agents/agents/*.md`): sub-agent role, tools, model profile. Use for agent habit across every stage it runs, whatever command it loads.
- **factory profile** (`.agents/factory/profiles.md`): checks, profile gates, detection, risk rules. Humans own it; propose only.

## Precision rule

Give each recommendation exactly one primary layer, mapped per Customization failures below. Use multiple layers for one issue only when responsibilities clearly split. No vague “update prompt and maybe add a skill” advice.

## What to evaluate

- Actual win condition?
- Validated, assumed, partially met, or not met?
- What concrete trace evidence proves it?
- Where did time go?
- Which loops, retries, or dead ends happened?
- Which failures came from missing role guidance, project context, reusable knowledge, agent habit, check, or stage setup?
- Which change most improves next rep?

## Diagnostic lens

### Validation failures
- “done” claimed without proof
- no explicit acceptance test
- validation too late
- weak or indirect evidence

### Planning / execution failures
- repeated exploration
- avoidable retries
- brittle assumptions
- unnecessary tool churn
- over-broad search before narrowing

### Customization failures
Map each issue:
- wrong global behavior -> `INSTRUCTIONS.md`
- missing repo rule/context -> `AGENTS.md`
- missing reusable procedure -> skill
- weak stage framing -> command
- wrong agent habit across stages -> agent
- missing or wrong check, gate, detection, or risk rule -> factory profile

## Recommendations standard

Recommendations: evidence-based, minimal, high leverage, directly implementable. Prefer few strong changes over long list.

Per edit, give target layer, why that layer is right, exact instruction (or skill/command summary), and how it would have changed this run.

## Output format

# Retrospective Report

## Outcome
State one:
- validated win
- apparent win
- partial
- failed

Add one-sentence explanation.

## Evidence from Trace
List strongest concrete observations from transcript, runs, and observability events.

## Where the Workflow Broke Down
Name main sources of time loss, ambiguity, retries, or unvalidated claims.

## Customization Diagnosis
Per major issue: target layer (Customization failures map) and why it is most precise.

## Recommended Changes
Only highest-leverage changes. Per change:
- **Target layer:** `INSTRUCTIONS.md` | `AGENTS.md` | skill | command | agent | factory profile
- **Change:** exact instruction, skill concept, or command behavior
- **Why:** what trace evidence justifies it
- **Expected effect on next rep:** reliability / speed / adaptability impact

## Prompt / Skill / Command Mutations
Concrete text or near-final draft for most important changes.

## Next Rep
Short improved workflow for next attempt: where validation happens, what to reuse.

## Quality bar
- Be specific.
- Use trace evidence.
- Pick right customization layer.
- Do not confuse project-wide rules with reusable skills.
- Do not confuse reusable skills with stage-specific commands.
- If trace is incomplete, say so explicitly.
