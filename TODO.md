# Orchestrate TODO

- [X] Fix lost web-manager lease handling so a manager stops accepting work and finalizes safely when renewal fails.
- [X] Fix task update/delete versus task-start TOCTOU races.
- [X] Serialize live-session event snapshot/persistence updates.
- [X] Make live-event visibility durable before SSE delivery.
- [X] Harden release workflow changelog and PyPI publish safety.
- [X] Resolve release-readiness docs/TODO contradictions.
- [X] Run final validation, update memory, and report handoff.
