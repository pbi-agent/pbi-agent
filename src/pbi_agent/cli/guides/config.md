# pbi-agent config

Manage the saved user-level configuration: maintenance retention, providers,
and model profiles.

## Purpose
`pbi-agent config` is the only CLI path that writes the saved internal config
file, `~/.pbi-agent/config.json` (override the location with the
`PBI_AGENT_INTERNAL_CONFIG_PATH` environment variable). The web UI Settings page
served by `pbi-agent web` writes the same file (providers, model profiles, the
default profile, maintenance). `run` and starting `web` only read it. The config
is per user, not per workspace: the current working directory does not matter.

Typical setup order: create a provider (how to connect), create a model profile
on top of it (which model and runtime settings), then select that profile as the
default. Use the web UI Settings page for the same data if you prefer a GUI.

## Usage
```text
pbi-agent config <scope> <action> [OPTIONS ...]
```

## Subcommands
- `pbi-agent config maintenance`: show or set daily maintenance data retention. Guide: `pbi-agent config maintenance --doc`.
- `pbi-agent config providers`: manage saved provider connection and auth settings. Guide: `pbi-agent config providers --doc`.
- `pbi-agent config profiles`: manage saved model profiles and the default profile. Guide: `pbi-agent config profiles --doc`.

A scope is required: `pbi-agent config` with no scope prints a usage error
(`the following arguments are required: <scope>`) and exits 2. Each scope also
requires an action. Append `--doc` to any scope or action for its guide.

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Create a provider, a profile on it, and make the profile the default
pbi-agent config providers create --name "OpenAI Main" --kind openai --api-key-env OPENAI_API_KEY
pbi-agent config profiles create --name analysis --provider-id openai-main --model gpt-5.4
pbi-agent config profiles select analysis
# Inspect what is saved
pbi-agent config providers list
pbi-agent config profiles list
pbi-agent config maintenance show
```

## Workflows
1. First-time setup: `pbi-agent config providers create ...`, then
   `pbi-agent config profiles create --provider-id ...` (the first profile
   becomes the default automatically), then `pbi-agent run -p "..."`.
2. Switch defaults: `pbi-agent config profiles list` to find IDs, then
   `pbi-agent config profiles select ID`. For a single run, use the global
   option instead: `pbi-agent --profile-id ID run -p "..."`.
3. Tighten disk usage: `pbi-agent config maintenance set --retention-days 7`,
   then confirm with `pbi-agent config maintenance show`.

## Related commands
- `pbi-agent run`: consumes the selected profile (or `--profile-id`).
- `pbi-agent web`: the browser UI uses the default profile and exposes the same
  settings in its Settings page.
- `pbi-agent sessions`: lists the session history that maintenance retention prunes.

## Pitfalls
- Validation and lookup failures (unknown ID, duplicate ID, invalid value) print
  `Error: ...` to stderr and exit 2, the same code argparse uses for usage errors.
- IDs are slugified: lowercase, with runs of non-alphanumeric characters turned
  into `-` (for example `"OpenAI Main"` becomes `openai-main`). ID arguments are
  slugified before lookup too.
- An unparseable `config.json` is read as empty and invalid entries are
  skipped silently; the next `config` write saves only what was readable. Back
  up a hand-edited file before running write commands.
- `config` commands do not resolve provider settings and need no API key.
- Global options such as `--verbose` go before `config`, not after it.
- The web UI Settings page edits the same file. CLI writes reload the file and
  replace it atomically without a revision check, so avoid editing the same
  item from both places at once.
