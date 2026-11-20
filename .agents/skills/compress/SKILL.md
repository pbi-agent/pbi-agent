---
name: compress
description: >
  Rewrite any text (pasted text, notes or files) into a
  compact, clear form that uses fewer tokens and keeps all content
  exact. Use when the user asks to compress, shorten, tighten, or simplify text.
---

# Compress

## Purpose

Rewrite text to be short, clear, and token-efficient. Keep every fact. Change only the wording.

## Input / Output

- **Pasted text** → return the compressed text in the reply. Do not create a file.
- **File path** → edit the file in place with normal file-editing tools.
- **Level** → use `standard` if the user does not give one.

| Level | Style | Use for |
|---|---|---|
| `light` | Plain Language. Full grammar, short sentences. | Text for humans: docs, emails, READMEs |
| `standard` | Terse. Drop articles and filler. Fragments OK. | Notes, prompts, agent instructions |
| `ultra` | Telegraphic. Symbols (`→`, `+`, `=`), abbreviations, key-value lines. | Memory files, context for agents only |

## Process

1. Read the full text. Find the main point and the audience (human or agent). Count the words in the original text (`before`).
2. Mark read-only regions (see Preserve).
3. Apply the Structure, Sentence, and Word rules to the prose.
4. Check: no lost facts, no changed meaning, read-only regions identical.
5. Count the words in the compressed text (`after`). Report:
   - Level used
   - Words: `before` → `after` (saved: `before - after`, `-X%`)
   - Any risky region left unchanged

## Structure Rules

- **BLUF**: put the conclusion, request, or main rule first.
- **Pyramid**: main idea → supporting points, grouped by topic.
- **Chunking**: one topic per paragraph or section. Max 6 sentences per paragraph.
- Use lists for parallel items, numbered steps for sequences, and tables for comparisons.
- Merge duplicate or overlapping bullets. Keep one example per pattern.
- Remove intros, outros, recaps, and sentences that repeat the heading.

## Sentence Rules (from ASD-STE100)

- Instructions: max 20 words. Descriptions: max 25 words.
- One instruction per sentence.
- Use the active voice: "Tests catch bugs", not "Bugs are caught by tests".
- Use the imperative for actions: "Run tests", not "You should run tests".
- Put conditions first: "If build fails, check logs."
- Put the warning before the step it applies to.
- Use one word for one meaning. Do not switch synonyms for the same thing.

## Word Rules

**Remove**
- Filler: just, really, basically, actually, simply, essentially, very
- Pleasantries: sure, certainly, of course, happy to
- Hedging: it might be worth, you could consider, it should be noted that
- Connective fluff: however, furthermore, additionally, moreover
- Directives: you should, make sure to, remember to, please
- Articles (a, an, the): remove at `standard` and `ultra` only

**Replace**
| Long | Short |
|---|---|
| in order to | to |
| due to the fact that | because |
| make a decision | decide |
| is able to | can |
| at this point in time | now |
| utilize / leverage | use |
| implement a solution for | fix |
| a large number of | many |

Use verbs, not noun forms: "configure", not "perform the configuration of".

## Preserve EXACTLY (read-only)

- Fenced code blocks and indented code
- Inline code in backticks
- URLs, links, file paths, commands, environment variables
- Technical terms, API and library names, proper nouns
- Numbers, dates, versions, units, IDs
- Frontmatter and YAML headers
- Quoted text, legal text, error messages
- Markdown headings (text unchanged) and list or table structure

Inside read-only regions, do not:
- remove comments or spacing
- reorder lines
- shorten or "simplify" anything

Do not merge sections across a code block.

## Safety

- Do not invent, add, or interpret facts. Compress wording only.
- Do not run scripts, CLIs, or network calls. Do not send text to external services.
- Do not compress code files, config files, secrets, or credentials (`.py`, `.js`, `.ts`, `.json`, `.yaml`, `.toml`, `.env`, `.sh`, `.sql`, `.html`, `.css`, `.xml`, `.lock`).
- If you are not sure whether a region is prose or code/config, leave it unchanged.
- If compressing would remove a nuance that matters (legal, safety, contract text), keep that nuance and report it.

## Examples

**standard**
> Original: You should always make sure to run the test suite before pushing any changes to the main branch. This is important because it helps catch bugs early and prevents broken builds from being deployed to production.
>
> Compressed: Run tests before push to main. Catches bugs early, prevents broken prod deploys.

**light**
> Original: Due to the fact that the API is able to return a large number of results, it is recommended that you utilize pagination.
>
> Compressed: The API can return many results. Use pagination.

**ultra**
> Original: The application uses a microservices architecture. The API gateway handles all incoming requests and routes them to the appropriate service. The authentication service manages user sessions and JWT tokens.
>
> Compressed: Arch: microservices. API gateway → routes all requests. Auth service → sessions + JWT.
