---
name: compress
description: >
  Compress natural-language memory files into a shorter caveman-style form to save
  input tokens while preserving technical substance, code, URLs, paths, commands,
  and structure. Use when a user asks to compress a memory or notes file.
---

# Compress

## Purpose

Compress natural-language files such as `md` files, notes, or preferences into shorter caveman-style prose to reduce input tokens.

## Process

1. Read the target file.
2. Compress only the prose. Do not invent, summarize away, or reinterpret technical content.
3. Preserve code, commands, URLs, paths, headings, and structural markers exactly.
4. Apply the edit directly with normal file-editing tools.
5. Report what changed and any residual risk if the file contains mixed prose and technical content.

## Compression Rules

### Remove
- Articles: a, an, the
- Filler: just, really, basically, actually, simply, essentially, generally
- Pleasantries: "sure", "certainly", "of course", "happy to", "I'd recommend"
- Hedging: "it might be worth", "you could consider", "it would be good to"
- Redundant phrasing: "in order to" → "to", "make sure to" → "ensure", "the reason is because" → "because"
- Connective fluff: "however", "furthermore", "additionally", "in addition"

### Preserve EXACTLY (never modify)
- Code blocks (fenced ``` and indented)
- Inline code (`backtick content`)
- URLs and links (full URLs, markdown links)
- File paths (`/src/components/...`, `./config.yaml`)
- Commands (`npm install`, `git commit`, `docker build`)
- Technical terms (library names, API names, protocols, algorithms)
- Proper nouns (project names, people, companies)
- Dates, version numbers, numeric values
- Environment variables (`$HOME`, `NODE_ENV`)
- Frontmatter/YAML headers in markdown files

### Preserve Structure
- All markdown headings (keep exact heading text, compress body below)
- Bullet point hierarchy (keep nesting level)
- Numbered lists (keep numbering)
- Tables (compress cell text, keep structure)

### Compress
- Use short synonyms: "big" not "extensive", "fix" not "implement a solution for", "use" not "utilize"
- Fragments OK: "Run tests before commit" not "You should always run tests before committing"
- Drop "you should", "make sure to", "remember to" — just state the action
- Merge redundant bullets that say the same thing differently
- Keep one example where multiple examples show the same pattern

CRITICAL RULE:
Anything inside ``` ... ``` must be copied EXACTLY.
Do not:
- remove comments
- remove spacing
- reorder lines
- shorten commands
- simplify anything

Inline code (`...`) must be preserved EXACTLY.
Do not modify anything inside backticks.

If file contains code blocks:
- Treat code blocks as read-only regions
- Only compress text outside them
- Do not merge sections around code

## Safety

- Do not run external scripts, CLIs, or network calls as part of this skill.
- Do not send file contents to third-party services for compression.
- If the file looks like code, config, secrets, credentials, or keys, do not compress it.
- If unsure whether a region is prose or executable/config data, leave it unchanged.

## Pattern

Original:
> You should always make sure to run the test suite before pushing any changes to the main branch. This is important because it helps catch bugs early and prevents broken builds from being deployed to production.

Compressed:
> Run tests before push to main. Catch bugs early, prevent broken prod deploys.

Original:
> The application uses a microservices architecture with the following components. The API gateway handles all incoming requests and routes them to the appropriate service. The authentication service is responsible for managing user sessions and JWT tokens.

Compressed:
> Microservices architecture. API gateway route all requests to services. Auth service manage user sessions + JWT tokens.

## Boundaries

- ONLY compress natural language files (.md, .txt, extensionless)
- NEVER modify: .py, .js, .ts, .json, .yaml, .yml, .toml, .env, .lock, .css, .html, .xml, .sql, .sh
- If file has mixed content (prose + code), compress ONLY the prose sections
- If unsure whether something is code or prose, leave it unchanged
- Do not create or rely on helper scripts for this skill

## MEMORY.md Mode

When target is `MEMORY.md`, compression means memory curation, not only prose shortening.

For `Long-Term Memory`:
- Keep only durable decisions, stable repo conventions, reusable validation patterns, and active follow-ups.
- Drop completed task logs, detailed histories, branch names, commit hashes, PR/run IDs, workflow IDs, validation transcripts, and implementation step lists unless still actionable.
- Prefer outcome-only bullets. Example: a detailed shipped-release log can become `v0.1.0 shipped.`
- If a bullet is only proof that past work happened, delete or collapse it.
- If a bullet tells future agents how to act, keep it compact.

`MEMORY.md` exception to normal preserve rules:
- Do not preserve every URL, path, command, date, version, or ID just because it is technical.
- Preserve technical strings only when they are needed for future decisions or workflows.

Acceptance check for `MEMORY.md`:
- `Long-Term Memory` should read like decisions/follow-ups, not changelog/docs.
- No completed-task bullet should contain a full chain of PR + branch + commit + workflow + validation details.
- Report compression by durable-memory impact, not by all removed details.