# pbi-agent config profiles

Manage saved model profiles: named runtime presets (model, reasoning, limits,
tool groups, compaction) tied to one saved provider.

## Purpose
A provider answers "how do I connect"; a model profile answers "which model and
runtime settings should this run use". Several profiles can share one provider
(for example `fast`, `analysis`, `review`). Profiles live in the
`model_profiles` list of `~/.pbi-agent/config.json`, and the default profile ID
is stored as `web.active_profile_id`.

At runtime the base profile is chosen from the global `--profile-id` option,
then the `PBI_AGENT_PROFILE_ID` environment variable, then the saved default.
Explicit CLI flags and environment variables are then layered on top of it.
`pbi-agent web` and new web sessions use the saved default.

## Usage
```text
pbi-agent config profiles <action> [OPTIONS ...]
```

## Subcommands
- `pbi-agent config profiles list`: show saved profiles and which one is the default. Guide: `pbi-agent config profiles list --doc`.
- `pbi-agent config profiles create`: add a profile on a saved provider. Guide: `pbi-agent config profiles create --doc`.
- `pbi-agent config profiles update`: change selected fields of a profile. Guide: `pbi-agent config profiles update --doc`.
- `pbi-agent config profiles delete`: remove a profile. Guide: `pbi-agent config profiles delete --doc`.
- `pbi-agent config profiles select`: set the default profile. Guide: `pbi-agent config profiles select --doc`.

An action is required: `pbi-agent config profiles` alone prints a usage error
(`the following arguments are required: <action>`) and exits 2.

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Two profiles on one provider, then pick the default
pbi-agent config profiles create --name fast --provider-id openai-main --model gpt-5.4-mini --reasoning-effort low
pbi-agent config profiles create --name analysis --provider-id openai-main --model gpt-5.4 --reasoning-effort xhigh
pbi-agent config profiles select analysis
pbi-agent config profiles list
# Use a non-default profile for one run
pbi-agent --profile-id fast run -p "Summarize README.md"
```

## Workflows
1. Read-only profile: create it with
   `pbi-agent config profiles create --name readonly --provider-id openai-main --allowed-tools read-image,web`,
   then run `pbi-agent --profile-id readonly run -p "..."`.
2. Retarget a profile to another provider:
   `pbi-agent config providers list`, then
   `pbi-agent config profiles update analysis --provider-id anthropic-main --model claude-opus-4-6`.
3. Retire a profile: `pbi-agent config profiles select OTHER_ID` if it is the
   default, then `pbi-agent config profiles delete OLD_ID`.

## Related commands
- `pbi-agent config providers`: a profile needs an existing saved provider.
- `pbi-agent run`: honors `--profile-id`, `PBI_AGENT_PROFILE_ID`, and the default.
- `pbi-agent web`: Settings manages the same profiles and default.

## Pitfalls
- The provider must exist and be an LLM kind (openai, azure, chatgpt,
  github_copilot, xai, google, google_gcp, anthropic, generic); speech-only
  providers are rejected.
- `--reasoning-mode` and `--service-tier` are only valid when the profile's
  provider kind is `openai`.
- Errors print `Error: ...` to stderr and exit 2. IDs are slugified, so
  `Analysis` and `analysis` refer to the same profile.
- Delete does not check references from project commands, sub-agents, or
  Kanban stages and tasks (`model_profile_id` and similar); those can dangle.
- Profile IDs cannot be changed after creation; `update --name` only changes
  the display name.
