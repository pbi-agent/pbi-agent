# pbi-agent init

Create a starter `AGENTS.md` file in the current working directory.

## Purpose
Bootstraps workspace instructions for the agent. The starter `AGENTS.md` contains
Memory, TODO, and Communication sections (how to keep `MEMORY.md`, `TODO.md`, and
how to report work). pbi-agent composes `AGENTS.md` into the runtime system prompt,
so edit the file afterwards to add project-specific guidance.

`init` only writes `AGENTS.md`. It does not install skills, commands, or sub-agents;
use `pbi-agent skills add`, `pbi-agent commands add`, `pbi-agent agents add`, or
`pbi-agent kits add` for those. It does not need provider settings or an API key.

## Usage
```text
pbi-agent init [--force]
```

## Options and arguments
- `--force, --overwrite`: replace an existing `AGENTS.md` with the starter template.
  Default: off, so an existing file is left untouched.

## Examples
```bash
# Create AGENTS.md in the current directory (skipped if it already exists)
pbi-agent init
# Replace an existing AGENTS.md with the starter template
pbi-agent init --force
```

## Workflows
1. Start a new workspace: `cd` into the project, run `pbi-agent init`, edit
   `AGENTS.md` to add project rules, then run `pbi-agent run -p "..."` or `pbi-agent web`.
2. Add reusable extensions after init: `pbi-agent skills add`, `pbi-agent commands add`,
   and `pbi-agent agents add` to install project-local items under `.agents/`.

## Related commands
- `pbi-agent kits add`: install a bundle of skills, commands, and agents.
- `pbi-agent skills add`, `pbi-agent commands add`, `pbi-agent agents add`: install individual items.
- `pbi-agent run`: run a prompt that uses the new `AGENTS.md`.

## Pitfalls
- The file is written to the current working directory; there is no
  `--project-dir` option. `cd` to the workspace root first.
- Without `--force`, an existing `AGENTS.md` is skipped and the command prints
  `Skipped AGENTS.md at <path>; already exists. Use --force to overwrite.` It still exits 0.
- `--force` overwrites the whole file with the template; customizations are lost.
- On success it prints `Created AGENTS.md at <path>` or `Overwrote AGENTS.md at <path>`.
