# Content Screen — Design (issue #5)

Date: 2026-09-30 · Status: Approved (user: "drive until PR ready", review at PR)
Branch: `feat/5-content-screen` · Evidence: `docs/research/2026-09-30-content-screen-spike.md`

## Problem

Tribunal gates tool calls (actions). Content that enters Claude's context unchecked:
third-party **skills** (can carry out-of-purpose instructions) and **web results**
(WebFetch/WebSearch can carry prompt injection).

## Decisions

- **Same script, dispatch on `hook_event_name`.** `hooks/tribunal.py` stays the single
  stdlib-only hook; `hooks/hooks.json` registers it for two more events. No new module.
- **Reuse the proven verdict shape.** Every screen asks one `choice` question with the
  existing labels `allowed` / `rejected` / `human_ask` (new instructions + criteria text), so
  `map_answer`, `extract_answer`, `real_post` and both provider envelopes are reused as-is.
  Issue #5 said `noul` for web; `choice` is used instead because its response shape is
  live-proven and `noul` is not.
- **Chunking, never truncation.** Content is split into ≤ `MAX_INPUT_BYTES` (8 KiB) UTF-8
  chunks on character boundaries; each chunk is one jev call; worst verdict wins
  (`deny` > `ask` > `allow`), `deny` short-circuits. A 15 s screen budget stops further
  chunks and yields `ask` (hook timeout is 30 s).
- **Skill verdicts cached by content.** Key = sha256 of `[model, min_confidence,
  question text, file text]`; only *clean* results are cached (empty marker file in
  `$XDG_CACHE_HOME/tribunal` or `~/.cache/tribunal`). Cache I/O errors are ignored — the
  cache is an optimisation, never a decision source on its own. API-key check stays before
  the cache so "no key → ask" is unchanged.
- **Unresolved skill = today's behaviour.** Built-in skills have no file; unknown or
  malformed names (anything but `[A-Za-z0-9_-][A-Za-z0-9_.-]*` with optional `plugin:` prefix)
  are not resolved. PreToolUse then falls through to the existing name-only jev verdict;
  UserPromptExpansion emits nothing.
- **Every matching skill file is screened.** No guessing Claude Code's precedence: all
  existing candidates are scanned, worst wins.

## Resolution (spike §1)

| Name | Candidates (`C` = `$CLAUDE_CONFIG_DIR` or `~/.claude`) |
|---|---|
| `x` | `C/skills/x/SKILL.md`, `C/commands/x.md`, `<cwd>/.claude/skills/x/SKILL.md`, `<cwd>/.claude/commands/x.md` |
| `p:x` | for every `installPath` under registry keys `p@*` in `C/plugins/installed_plugins.json`: `<installPath>/skills/x/SKILL.md`, `<installPath>/commands/x.md` |

## Behaviour per event

`TRIBUNAL_SCAN`: unset/empty → `skills,web`; `skills` / `web` / `skills,web` → those;
`off` → none; anything else → both (fail tight).

| Event | Scope | Clean | Flagged (`rejected`) | Uncertain / error / no key |
|---|---|---|---|---|
| PreToolUse `Skill` | skills | `allow` | `deny`, reason to Claude | `ask` |
| UserPromptExpansion | skills | no output | `{"decision":"block","reason"}` (spike §3: works) | `systemMessage` warning to user, command runs (native behaviour) |
| PostToolUse `WebFetch`/`WebSearch` | web | no output | `additionalContext` warning (spike §5: reaches Claude) | `additionalContext` "unscreened" warning |

Scope disabled → PreToolUse `Skill` uses today's name-only verdict; the other two events
emit nothing and make no network call.

Web content = `tool_response["result"]` when it is a string (WebFetch), else
`json.dumps(tool_response)` (WebSearch). Content is warned about, never replaced
(`updatedToolOutput` left for later: a false positive would hide a real page).

## Failure paths

`main()` keeps its shape; the known-error fallback becomes event-aware:
PreToolUse → `ask`; PostToolUse → unscreened `additionalContext`; UserPromptExpansion →
`systemMessage` warning. Unexpected exceptions still exit 1 (non-blocking, native flow).

## Out of scope (issue follow-ups)

`Read` of skill reference files; `Read` outside the project; plugins with custom skill paths
in `plugin.json` (they resolve as "unresolved" → today's behaviour); larger chunk budget.
