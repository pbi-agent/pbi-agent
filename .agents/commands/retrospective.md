---
name: retrospective
description: Retrospective Mode
---

# Retrospective Mode

Evaluate workflow that just happened and identify most precise customization change for next rep.

Do not continue task. Inspect completed workflow, use local session trace as evidence, and recommend improvements at correct pbi-agent customization stack layer.

## Mission

Turn one workflow run into better next run.

Optimize for:
1. reliability
2. wall-clock time
3. adaptability to a changing codebase

Do not invent success. Determine whether workflow closed loop.

## Primary evidence sources

Use concrete evidence first, narrative second.

Inspect:
- resumed session transcript
- local SQLite session database
- latest run chain for current workflow/session
- relevant workspace customization files if present

Find the session database from:
1. `PBI_AGENT_SESSION_DB_PATH` if set
2. otherwise `~/.pbi-agent/sessions.db`

Prefer current/resumed `session_id`. If multiple runs exist, focus latest run chain tied to this workflow pass.

Relevant tables may include:
- `sessions`
- `messages`
- `run_sessions`
- `observability_events`
- `kanban_tasks`
- `kanban_stage_configs`

## The pbi-agent customization stack

When recommending improvements, classify into correct layer instead of generic advice.

### 1) `INSTRUCTIONS.md` — workspace role / main prompt system

Treat `INSTRUCTIONS.md` as workspace main role definition and operating contract.

Use this layer for problems like:
- agent chose wrong overall strategy
- agent was too passive or too eager
- agent did not prioritize validation enough
- agent used tools in wrong general way
- agent should consistently think in different mode across whole project

Recommend `INSTRUCTIONS.md` changes only when improvement should apply to nearly every workspace task.

### 2) `AGENTS.md` — project context and repository rules

Treat `AGENTS.md` as project-specific rules and conventions layer.

Use this layer for problems like:
- missing repo conventions
- missing test / validation commands
- missing architecture context
- incorrect assumptions about directories, ownership, boundaries, or workflows
- policies every session in this repo should follow

Recommend `AGENTS.md` changes when lesson is repo-specific and should be available in all sessions.

### 3) Skills — reusable knowledge base / workflow recipes

Treat skills as reusable know-how agent can load when task matches recurring workflow.

Use skill when run revealed:
- repeated multi-step procedures
- stable reusable workflows
- domain-specific troubleshooting playbooks
- validation recipes
- environment-specific operational knowledge
- decision trees too detailed for `AGENTS.md`

Recommend new skill or skill update when lesson is procedural knowledge reused selectively, not forced into every prompt.

### 4) Commands — stage-specific prompt presets

Treat commands as stage-entry behavior presets, especially kanban stages.

Use command when improvement is about:
- how stage should start
- what stage should focus on
- what inputs to inspect first
- how to format outputs for that stage
- what “done” means for that stage

Recommend command changes when fix is specific to workflow step such as execute, validate, review, or retrospective.

## Precision rule

For every recommendation, choose exactly one primary layer:
- `INSTRUCTIONS.md`
- `AGENTS.md`
- skill
- command

Only recommend multiple layers for same issue when responsibilities clearly split. Avoid vague “update prompt and maybe add a skill” advice.

## What to evaluate

Figure out:
- Actual win condition?
- Validated, assumed, partially met, or not met?
- What concrete trace evidence proves it?
- Where did time go?
- Which loops, retries, or dead ends happened?
- Which failures came from missing role guidance, missing project context, missing reusable knowledge, or weak stage setup?
- Which change most improves next rep?

## Diagnostic lens

Look for these failure classes:

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
Map each issue precisely:
- wrong global behavior -> `INSTRUCTIONS.md`
- missing repo rule/context -> `AGENTS.md`
- missing reusable procedure -> skill
- weak stage framing -> command

## Recommendations standard

Recommendations must be:
- evidence-based
- minimal
- high leverage
- specific enough to implement directly

Prefer few strong changes over long list.

When proposing edits:
- give target layer
- explain why that layer is right
- write exact instruction or summary of skill/command to add
- describe how it would have changed this run

## Output format

# Retrospective Report

## Outcome
State one:
- validated win
- apparent win
- partial
- failed

Give one-sentence explanation.

## Evidence from Trace
List strongest concrete observations from transcript, runs, and observability events.

## Where the Workflow Broke Down
Call out main sources of time loss, ambiguity, retries, or unvalidated claims.

## Customization Diagnosis
For each major issue, classify correct target layer:
- `INSTRUCTIONS.md`
- `AGENTS.md`
- skill
- command

For each classification, explain why this is most precise layer.

## Recommended Changes
Provide only highest-leverage changes.

For each change, use this format:
- **Target layer:** `INSTRUCTIONS.md` | `AGENTS.md` | skill | command
- **Change:** exact instruction, skill concept, or command behavior
- **Why:** what trace evidence justifies it
- **Expected effect on next rep:** reliability / speed / adaptability impact

## Prompt / Skill / Command Mutations
Write concrete text or near-final draft for most important changes.

## Next Rep
Give short improved workflow for next attempt, including where validation happens and what should be reused.

## Quality bar
- Be specific.
- Use trace evidence.
- Pick the right customization layer.
- Do not confuse project-wide rules with reusable skills.
- Do not confuse reusable skills with stage-specific commands.
- If trace is incomplete, say so explicitly.
