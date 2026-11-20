---
id: gh-455
type: bug_fix
type_reason: Label bug; Enhance prompt fails with GitHub Copilot 400 (tool choice sent without tools), existing behavior wrong, no new capability.
source: https://github.com/pbi-agent/pbi-agent/issues/455
risk: high
risk_triggers: provider request paths (src/pbi_agent/providers/)
stage: done
status: done
---
# Fix "Enhance prompt" failing with tools-required 400 on no-tool provider calls

## Goal
Enhance prompt (wand button / Ctrl+Space in the web composer) works with GitHub Copilot, and every supported provider backend (OpenAI, xAI, Google Gemini, Anthropic, ChatGPT/Codex, GitHub Copilot, generic OpenAI-compatible) sends a valid request when a call has no tools: no tool choice on a tool-less request. Full requirements and scope: issue #455 (`gh issue view 455 --json body`).

## Acceptance criteria
1. Live check against a real GitHub Copilot account: Enhance prompt on a normal draft succeeds and returns rewritten text without the 400 error.
2. No provider sends a tool choice on a request that has no tools; provider tests cover the no-tools request shape for each changed provider (in its `tests/test_<provider>_provider.py`) and pass.
3. Requests that do have tools keep their current tool behavior on every provider; existing tests for tool-using turns still pass.
4. Repo checks for the touched surfaces pass (`uv run ruff check .`, `uv run ruff format --check .`, `uv run basedpyright`, `uv run pytest`).

Out of scope: changing Enhance prompt rewrite instructions or output, composer error display, normal tool-using agent turns, new providers or settings.

## Links
- Issue: https://github.com/pbi-agent/pbi-agent/issues/455
- Providers: `src/pbi_agent/providers/`; tests `tests/test_*_provider.py`

## Environment notes (intake)
- Branch `master`, clean tree, in sync with origin/master (no unpushed commits).
- Local `~/.pbi-agent/config.json` has a `github_copilot` provider (id `copilot`) for the live check.
- Conductor runs in Claude Code: stage agents are Agent-tool sub-agents told to follow `.agents/agents/<name>.md` and its referenced `.agents/commands/<cmd>.md`.

## Stage files
- task: task.md
- triage: triage.md
- plan: plan.md
- build: build.md
- review: review-1.md
- quality: quality-1.md
- quality-2: quality-2.md
- fix: fix-1.md
- verify: verify.md
- release: release.md
- learn: learn.md

## Gate log
| stage | gate | decision | note |
| --- | --- | --- | --- |
| intake | always_run | auto_pass | type bug_fix (label bug), risk high (providers) |
| triage | approve | approved_unchanged | triage: proceed; reproduced offline (Copilot chat body tools [] + tool_choice auto); Codex tool_choice + Responses parallel_tool_calls also no-tools; profile/risk unchanged |
| plan | approve | approved_unchanged | plan: ready; 5 builders drop tools/tool_choice/parallel_tool_calls when no tools; byte-for-byte tool-using diff; live Copilot enhance check |
| build | always_run | auto_pass | conductor reran ruff check, format --check, basedpyright (0 errors), full pytest 2533 passed/9 skipped: green; diff 5 src (+17/-1) + 5 test files; risk stays high (providers); conductor ran `ruff format` on triage.md (ruff formats Python fences in .md; would fail CI format check) |
| review | approve | approved_unchanged | human: Approve and release |
| release | approve | approved_unchanged | human: Approve and release; no unpushed base commits |
| verify | always_run | auto_pass | verify: pass; full validation green; live Copilot enhance + tool turn pass; all 4 AC confirmed |
| learn | always_run | auto_pass | learn: 4 proposals; ledger rows appended; no gate eligible for promotion |

## Stage log
| stage | round | result | note |
| --- | --- | --- | --- |
| review | reviewer r1 | No findings. | tool-using bodies sha256 unchanged; enhance/compaction send no tool history; 5 provider tests + prompt_enhancement rerun (225 passed) |
| review | code-quality r1 | findings: 1 | Copilot chat body duplicates generic builder; reuse protocol.build_request_body |
| review | fix-1 | fix: done | Copilot chat uses protocol.build_request_body; sorted-JSON bodies identical; other builders sha256 unchanged |
| review | validation | pass | conductor reran ruff check, format --check, basedpyright 0 errors, full pytest 2533 passed/9 skipped |
| review | code-quality r2 | No code-quality findings. | quality-1 resolved; agent reviewers clean |
| verify | validation+live | verify: pass | full pytest/ruff/basedpyright green; live Copilot enhance 200 (no tool fields on wire) + live Copilot tool turn 200 |
| release | operator | release: shipped | PR #456 merged 79c3a32a; PR checks + post-merge CI (Tests, Deploy Docs) green; #455 closed, one comment |

Learn proposals 1-4 applied on human request (2026-11-20); proposal 1 also mirrored into `plan-interactive.md`; verify skill recipe re-tested live (port 7457: PID = uv, cwd correct, kill frees port).
