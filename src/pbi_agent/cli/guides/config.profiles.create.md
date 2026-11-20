# pbi-agent config profiles create

Create a saved model profile on an existing saved provider.

## Purpose
Adds a profile to `~/.pbi-agent/config.json` and prints
`Created model profile 'ID'.` The profile stores runtime settings only; the
connection and credentials come from the referenced provider. If no default
profile is set yet, the new profile automatically becomes the default. Use
`pbi-agent config profiles update` to change an existing profile instead.

## Usage
```text
pbi-agent config profiles create --name NAME [--id ID] --provider-id PROVIDER_ID [--model MODEL] [--sub-agent-model SUB_AGENT_MODEL] [--reasoning-effort REASONING_EFFORT] [--reasoning-mode {standard,pro}] [--max-tokens MAX_TOKENS] [--service-tier {auto,default,flex,priority}] [--allowed-tools ALLOWED_TOOLS] [--max-tool-workers MAX_TOOL_WORKERS] [--max-retries MAX_RETRIES] [--compact-threshold COMPACT_THRESHOLD] [--compact-tail-turns COMPACT_TAIL_TURNS] [--compact-preserve-recent-tokens COMPACT_PRESERVE_RECENT_TOKENS] [--compact-tool-output-max-chars COMPACT_TOOL_OUTPUT_MAX_CHARS]
```

## Options and arguments
Unset optional fields are stored empty, and the provider or runtime default applies.
- `--name NAME` (required): display name; must not be blank.
- `--id ID`: stable ID; defaults to the slugified `--name` (`"Deep Review"` becomes `deep-review`).
- `--provider-id PROVIDER_ID` (required): saved provider ID; must exist and be an LLM provider kind.
- `--model MODEL`: main model; unset means the provider default.
- `--sub-agent-model SUB_AGENT_MODEL`: model for the `sub_agent` tool; unset uses the profile's main model.
- `--reasoning-effort REASONING_EFFORT`: free-form, passed to the provider (for example `low`, `medium`, `high`, `xhigh`).
- `--reasoning-mode {standard,pro}`: OpenAI Responses reasoning mode; provider kind must be `openai` and the model (and sub-agent model) must support it.
- `--max-tokens MAX_TOKENS`: output token cap, >= 1 (runtime default 16384).
- `--service-tier {auto,default,flex,priority}`: OpenAI service tier; provider kind must be `openai`.
- `--allowed-tools ALLOWED_TOOLS`: comma-separated built-in tool groups: `read-image` (alias `read`), `write`, `web`, `sub-agent`, `shell`. Unset allows all; an empty string allows none of them.
- `--max-tool-workers MAX_TOOL_WORKERS`: parallel tool workers, >= 1 (default 4).
- `--max-retries MAX_RETRIES`: retries for transient provider errors, >= 0 (default 3).
- `--compact-threshold COMPACT_THRESHOLD`: context-token compaction threshold, >= 0 (default 200000).
- `--compact-tail-turns COMPACT_TAIL_TURNS`: recent user turns kept verbatim after compaction, >= 0 (default 2).
- `--compact-preserve-recent-tokens COMPACT_PRESERVE_RECENT_TOKENS`: token budget for that preserved tail, >= 0 (default 8000).
- `--compact-tool-output-max-chars COMPACT_TOOL_OUTPUT_MAX_CHARS`: max characters per tool result in compaction prompts, >= 0 (default 2000).

## Examples
```bash
# Minimal profile using the provider's default model
pbi-agent config profiles create --name default --provider-id openai-main
# Analysis profile with an explicit ID and sub-agent model
pbi-agent config profiles create --name "Deep Analysis" --id analysis --provider-id openai-main --model gpt-5.4 --sub-agent-model gpt-5.4-mini --reasoning-effort xhigh
# Read-only profile: no write or shell tools
pbi-agent config profiles create --name readonly --provider-id anthropic-main --allowed-tools read-image,web
```

## Workflows
1. New provider plus profile: `pbi-agent config providers create --name "OpenAI Main" --kind openai`,
   then `pbi-agent config profiles create --name analysis --provider-id openai-main`,
   then `pbi-agent run -p "..."` (the first profile is already the default).
2. Additional profile: create it, then `pbi-agent config profiles select ID`
   to make it the default, or pass `pbi-agent --profile-id ID run ...` per run.

## Related commands
- `pbi-agent config providers create`: create the provider first.
- `pbi-agent config profiles update`: change fields later.
- `pbi-agent config profiles select`: make it the default.

## Pitfalls
- Validation errors print `Error: ...` and exit 2, for example
  `Profile 'analysis' already exists.`, `Unknown provider ID 'x'.`, or a
  reasoning mode / service tier used with a non-OpenAI provider.
- An existing default is not replaced; run `select` to switch it.
- Unknown `--allowed-tools` groups are rejected; `ask-user` is not a profile group.
