# Orchestrate TODO

- [X] Make terminal live-session finalization persistence failure-safe.
- [X] Make task start setup crash-recoverable and internally consistent.
- [X] Prevent lease release while non-cooperative workers can still mutate state.
- [X] Make live-session recovery retry-safe after snapshot refetch failures.
- [X] Harden release workflow partial-release recovery.
- [X] Run final validation, update memory, and report handoff.
