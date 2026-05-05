[X] Parent orchestration: split `src/pbi_agent/web/session_manager.py` into utility-scoped `src/pbi_agent/web/session/` modules with no behavior changes; review and validate each worker
[X] Worker state: extract constants/date helpers and state dataclasses/stream primitives to `session/state.py`
[X] Worker serializers: extract pure serialization/status/image/timeline helpers to `session/serializers.py`
[X] Worker catalogs: extract file mention/bootstrap/slash-command methods to `session/catalogs.py`
[X] Worker saved_sessions: extract saved session CRUD/detail/run/dashboard methods to `session/saved_sessions.py`
[X] Worker live_sessions: extract live session/input/upload/question/shell/profile/binding/projection methods to `session/live_sessions.py`
[X] Worker events: extract app/session stream replay/persisted-event/publish/apply methods to `session/events.py`
[X] Worker tasks: extract Kanban board/task CRUD/run/prompt/stage/event helpers to `session/tasks.py`
[X] Worker workers: extract background worker/shutdown/lease/finalize helpers to `session/workers.py`
[X] Worker configuration: extract provider/model profile/runtime/config command-map methods to `session/configuration.py`
[X] Worker provider_auth: extract provider auth CRUD/status/flow/helpers to `session/provider_auth.py`
[X] Parent facade: shrink `session_manager.py` to stable public facade inheriting the mixins
[X] Review worker outputs for scoped edits/import ownership/no logic drift
[X] Validate Ruff and focused backend tests
[X] Update MEMORY.md
