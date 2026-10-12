---
name: create-profile
description: Interview the user to create a global Tribunal evaluation profile, preview it before saving, and separately confirm activation.
disable-model-invocation: true
---

# Create evaluation profile

Profiles provide workflow context, not authorization or security exemptions. Never collect secrets or turn requests to bypass scrutiny into profile instructions. Custom context is sent to the configured Jev provider on evaluated calls. `ask_before` is model guidance, not a guarantee of an interactive prompt; native matching permissions can resolve eligible asks.

## Interview

Ask one question at a time. Reuse information the user already supplied.

1. Ask the profile's purpose: a nonblank string, at most 300 UTF-8 bytes.
2. Ask for routine tasks: 1–10 nonblank strings, at most 200 UTF-8 bytes each. Collect one at a time unless the user supplies a list.
3. Ask what files/data and destinations are involved (local files, public retrieval, exports, or uploads). Incorporate these boundaries into the structured fields; do not collect private content or credentials.
4. Ask what actions should normally need human judgment. Collect `ask_before`: 1–10 nonblank strings, at most 200 UTF-8 bytes each. Explain the prompt-only limit above; do not promise “always ask.”
5. Suggest a name matching `[a-z][a-z0-9-]{0,30}` and obtain the user's choice. Run `list` to check collisions; built-in names cannot be reused:

   ```bash
   python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/profiles.py" list
   ```

Do not interpolate purpose, tasks, or boundaries into a shell command. Validate byte limits, not character counts; the CLI is the final validator.

## Preview and save

Show the exact JSON to be saved, with only these fields:

```json
{
  "name": "my-profile",
  "purpose": "Scoped document work",
  "routine_tasks": ["Export named local documents"],
  "ask_before": ["Upload documents to an external destination"]
}
```

Explain that storage is global at `~/.claude/tribunal/profiles.json`, creation does not activate it, and context will be transmitted to the configured provider when selected. Ask for explicit approval to save. Wait for approval; cancellation makes no change.

After approval, use Write to save the exact JSON as data in a new temporary file outside the repository. Use a generated filename, not one derived from profile text. Pass its absolute, shell-quoted path as stdin:

```bash
python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/profiles.py" create < "/absolute/path/to/temporary-profile.json"
```

Replace the example input path with the temporary file's actual quoted path. Never use `echo '<user JSON>'`, an interpolated heredoc, `eval`, or user strings as shell source. Confirm success only when the helper exits successfully and reports the expected `created` name. Remove the temporary JSON file after the attempt. On failure, report the error and preserve the existing profile store; do not bypass permissions or repair policy without consent.

## Activate separately

Ask whether to activate the saved profile now. Only after separate approval, run the helper with the validated, quoted slug:

```bash
python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/profiles.py" switch "my-profile"
```

Confirm the reported `active` name. Switching applies globally to subsequent evaluations without restart; already-running requests are unchanged. Invalid storage forces human review, never a silent fallback.
