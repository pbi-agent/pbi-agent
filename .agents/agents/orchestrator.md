---
name: orchestrator
description: Run one implementation task through an optional initial planning step, then mandatory sequential worker, reviewer/fixer, and code-quality/fixer loops.
model_profile_id: worker-pro
allowed_tools: read,write,shell,sub-agent,web
commands: orchestrate
sub_agents: planner,worker,reviewer,code-quality-reviewer,fixer
---
