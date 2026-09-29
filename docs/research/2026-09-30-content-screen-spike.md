# Content-Screen Spike — Hook Payload Evidence (issue #5)

Date: 2026-09-30 · Claude Code 2.1.284 · Branch: `feat/5-content-screen`

Method: headless `claude -p` sessions with a throwaway `--settings` file (tribunal
plugin disabled, log-only hooks appending stdin to `/tmp/tribunal-spike.jsonl`).
Global settings were never edited; all spike files were deleted afterwards.
`session_id`, `transcript_path`, `cwd` omitted below.

## 1. `Skill` tool input is the name only

PreToolUse, user skill:

    {"hook_event_name": "PreToolUse", "tool_name": "Skill", "tool_input": {"skill": "clean-code"}}

PreToolUse, plugin skill — namespaced `plugin:skill`:

    {"hook_event_name": "PreToolUse", "tool_name": "Skill",
     "tool_input": {"skill": "superpowers:verification-before-completion"}}

→ The hook must resolve the file itself. Plugin install paths live in
`~/.claude/plugins/installed_plugins.json` (`plugins["<name>@<marketplace>"][].installPath`);
several versions can coexist in the cache (superpowers 6.3.0 and 6.4.1), only the
registry entry names the live one.

## 2. PostToolUse on `Skill` does NOT carry the body

    {"hook_event_name": "PostToolUse", "tool_name": "Skill", "tool_input": {"skill": "clean-code"},
     "tool_response": {"success": true, "commandName": "clean-code", "allowedTools": ["Read", "Write", "Edit"]}}

→ Scanning must happen in PreToolUse, from the file on disk.

## 3. `UserPromptExpansion` has no expanded text

    {"hook_event_name": "UserPromptExpansion", "expansion_type": "slash_command",
     "command_name": "clean-code", "command_args": "say hi", "command_source": "userSettings",
     "prompt": "/clean-code say hi"}

Plugin command: `"command_name": "superpowers:verification-before-completion", "command_source": "plugin"`.

- `{"decision": "block", "reason": "..."}` **works**: the prompt never reaches Claude and
  the reason is shown to the user.
- `hookSpecificOutput.additionalContext` on this event did **not** reach Claude (secret-word
  probe answered `NONE`). Do not rely on it.

## 4. WebFetch / WebSearch `tool_response` shapes

    WebFetch:  {"bytes": 713, "code": 200, "codeText": "OK",
                "result": "<summary text produced by the fetch model>", "durationMs": 4269,
                "url": "https://example.com"}
    WebSearch: {"query": "example domain iana", "results": [], "durationSeconds": 2.34, "searchCount": 0}

Note: WebFetch `result` is the fetch model's summary, not raw HTML. Injected text can
survive summarisation, so the summary is what reaches Claude and what must be screened.

## 5. PostToolUse `additionalContext` reaches Claude

Hook output:

    {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                            "additionalContext": "Tribunal note: the secret word is MANGO."}}

The session's final answer was `MANGO`. The warning channel for web content is proven.
