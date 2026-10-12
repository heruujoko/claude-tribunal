---
name: profile
description: Switch the active evaluation profile for Tribunal. Lists available profiles (developer, office-design, browsing, and any custom profiles), shows the current active profile, and switches to a user-selected profile. Changes apply globally to all subsequent Tribunal evaluations without restart.
disable-model-invocation: true
---

# Switch evaluation profile

Show or change the active evaluation profile. Changes apply globally to all subsequent Tribunal evaluations without restart.

## Commands

### List all profiles

    python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/profiles.py" list

Output: JSON with `active`, `builtin` (developer, office-design, browsing), and `custom` (user-defined profiles).

### Show active profile

    python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/profiles.py" show

Output: JSON with `active` field naming the current profile.

### Switch profile

    python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/profiles.py" switch NAME

Where `NAME` is one of: `developer`, `office-design`, `browsing`, or any custom profile name.

Output: JSON with `active` field confirming the switch.

## Workflow

1. Run `list` to show available profiles and the current active profile.
2. Ask the user which profile to switch to.
3. Run `switch NAME` with the user's choice.
4. Confirm the switch succeeded (output shows the new active profile).

## Notes

- The switch applies globally to all Tribunal sessions; no restart needed.
- The next evaluation reads the updated profile from `~/.claude/tribunal/profiles.json`.
- If the profile file is corrupted, Tribunal asks the human (fail-to-human).
- Custom profiles must be created separately via the `create-profile` skill.
- Pass only a validated profile slug as `NAME`, quoted as a single argument; never execute user text as shell source.
- Profiles are context, not authorization. Do not bypass a permission prompt to manage profiles.
- `ask_before` is model guidance, not a guaranteed prompt; explicit native permissions can resolve eligible asks.
