# Review: gh-449, round 2

review: No findings.

Scope: the round 1 fix (`src/pbi_agent/cli/guides/pbi-agent.md`, `src/pbi_agent/cli/guides/config.md`) and the conductor addition (`docs/environment.md`). Areas round 1 cleared and the fix did not touch were not reviewed again. Out of scope: `.agents/**`, `MEMORY.md`, `TODO.md`.

## Verification performed
- Round 1 finding (P3, `web` never writes config): fixed.
  - `pbi-agent.md:75` now says saved config is written only by `pbi-agent config ...` and the web UI Settings page, and that `run` and starting `web` only read it.
  - `config.md:7-12` keeps "the only CLI path that writes" and adds that the web Settings page writes the same file.
  - I checked this against the code. Every `save_internal_config_with_revision` caller in `src/pbi_agent/config.py` (create/replace/delete provider and profile, `select_active_model_profile`, `select_stt_provider`, `select_prompt_enhancement_profile`, `update_maintenance_config`, `update_user_profile_config`) is reached only from `src/pbi_agent/cli/config.py` and `src/pbi_agent/web/session/configuration.py` (via `web/api/routes/config.py`). So "only CLI path" and "only `config` commands plus web Settings" are both accurate.
  - Telegram channel config goes to the session store (`channels/manager.py`), not `config.json`, so the claim still holds for `channels telegram configure`.
  - Both sentences now agree with `config.md:74` ("The web UI Settings page edits the same file"), `config.maintenance.md:57` and `config.providers.md:70`, which removes the round 1 contradiction.
- `docs/environment.md:20`: the `PBI_AGENT_REASONING_EFFORT` default is now `medium`.
  - `_default_reasoning_effort` (`config.py:1807`) ignores `provider_kind` and returns `"medium"`. It is the only default source (call sites `config.py:1636,1909,2018`).
  - The page now matches `docs/cli.md:41` and the root guide (`pbi-agent.md:47`).
  - The remaining `xhigh` hits in `docs/` and the guides are example values or choice lists, not defaults.
- `uv run pytest -q --tb=short -x tests/cli`: pass.
- `uv run pbi-agent config --doc` renders the updated Purpose section.
- Non-blocking note (not a finding):
  - The parenthetical list of what web Settings writes ("providers, model profiles, default profile, maintenance") in both guides is not complete. Web Settings also writes the user profile, the speech-to-text provider selection and the prompt-enhancement profile (`configuration.py:184,544,560`).
  - The main claim (who writes the file) is correct, and the list reads as examples, so I am not flagging it.

### Findings

No findings.

### Overall Correctness
- overall_correctness: patch is correct
- overall_explanation: The round 1 wording issue is fixed accurately in both guides and matches the code's actual config writers. The `docs/environment.md` default now matches `_default_reasoning_effort` and `docs/cli.md`. The fix introduced no new inaccuracy, and the CLI tests pass.
- overall_confidence_score: 0.9
