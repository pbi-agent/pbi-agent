# TODO

[X] Prevent `run_task()` from racing with shutdown before worker registration
[X] Ensure `run_task()` setup failures always clear `_running_task_ids`
[X] Improve SSE overflow recovery cursor/id semantics
[X] Validate `oldest_available_seq` in frontend replay parser
[X] Run final validation and update memory
