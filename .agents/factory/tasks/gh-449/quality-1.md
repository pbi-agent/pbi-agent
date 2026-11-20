# Code quality review: gh-449, round 1

quality: findings: 1

Scope: `src/pbi_agent/cli/doc.py`, `src/pbi_agent/cli/parser.py` (diff), `src/pbi_agent/cli/guides/*.md` (56), `tests/cli/test_doc.py`, `docs/cli.md`, `docs/environment.md`. Out of scope: `.agents/**`, `MEMORY.md`, `TODO.md`.

### Code Quality Findings

- title: Make the guide-to-parser sync guard bidirectional
- severity: major
- file:line: tests/cli/test_doc.py:316
- issue: `test_guide_documents_every_option` only checks parser-to-guide. When a flag is removed or renamed, or a usage line changes, the old text stays in 56 hand-written Usage and Options sections and no test fails.
- fix: Add the reverse check: every `-x`/`--flag` token in a guide's Usage and Options sections must exist on that parser, its parents or the root. Also compare the normalized Usage block with `format_usage()`.

Evidence (scratch check, not committed):
- A reverse token scan finds only 6 paths with tokens that are not on their own parser: `sandbox` `-e`, `hooks trust/enable/disable` `--json`, `channels telegram` `--token-env-var`/`--token-secret`, `channels telegram restart` `--port`. So the check is practical with a parent-options allowance plus a small explicit allowlist.
- 14 Usage blocks differ from the argparse usage line. The differences are intentional: `[GLOBAL OPTIONS]` prefixes, the `update` alias line, and the root `--doc` line. A comparison would need to normalize those away, or use one documented prefix rule.

### Overall Assessment

The patch is maintainable enough to land: `doc.py` and the parser hook are small idiomatic argparse. The one gap is the one-way drift guard over 56 hand-written guides.
