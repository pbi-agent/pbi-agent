---
name: "tldr"
description: "Compress the previous assistant message into a very compact tldr. Use only when the user types /tldr explicitly."
---

# tldr

The user typed /tldr because the last answer was too long to read. Rewrite that answer as the shortest version that still lets them act on it.

## What to compress

Compress the most recent assistant message, the one right before /tldr. If text follows /tldr (e.g. `/tldr the install part`), compress only that part of the message. Do not summarize the whole conversation, and do not add anything that wasn't in the message.

## Length: scale with the original

- Short or single-point answer → one line.
- Medium answer → 2–3 bullets.
- Long, multi-part answer → at most ~5 bullets. If it really has more parts, merge the minor ones; don't go past ~7.

The Next steps line (below) doesn't count toward these limits.

Aim for roughly 10–20% of the original's length. If the tldr isn't clearly shorter than the original, cut harder.

## What to keep

The user reads the tldr instead of the original, so it has to keep anything they'd need to act on:

- **The answer or conclusion first**: the recommendation, verdict, or result.
- **Exact specifics that matter**: commands, file names, numbers, dates, prices, versions, names, and the key link. Copy these exactly; a paraphrased command or a rounded number is worse than useless.
- **Warnings and caveats** that change what the user should do (e.g. "back up first", "only works on v3+").
- **Next steps**: always keep them when the original has any, including action items, open questions waiting on the user, and offers of what to do next. They are often the most useful part of a long answer, so never drop them to save space. Put them in a final `**Next:**` line, terse and in order (`**Next:** run migration → restart app → confirm logs`). If the original had no next steps, leave the line out and don't make any up.

## What to drop

Background, reasoning, examples, restated context, hedging, pleasantries, alternatives the original ruled out, and long code blocks. For code, keep only the one line or command the user actually needs, and leave out the full listing.

## Format

- Start with `**TL;DR:**` followed by the one-liner, or by the bullets on the next lines.
- End with the `**Next:**` line when there are next steps.
- Terse fragments are fine ("Use X, not Y"). Skip filler words.
- Keep inline `code` formatting for commands and paths.
- No preamble ("Here's a summary…") and no closing offer of your own. Output the tldr and nothing else.
- Write in the same language as the original message.

## Example

Original (long answer about fixing a slow Postgres query, ~400 words covering EXPLAIN output, index theory, two rejected options, a migration caveat, and closing steps to deploy and verify).

tldr:

**TL;DR:**
- Cause: sequential scan on `orders.customer_id`
- Fix: `CREATE INDEX CONCURRENTLY idx_orders_customer ON orders(customer_id);`
- Expected: ~2s → <50ms
- Use `CONCURRENTLY` in prod, or the table locks during the build

**Next:** run on staging → check `EXPLAIN ANALYZE` uses the index → deploy to prod