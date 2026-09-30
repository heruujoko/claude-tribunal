# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code **plugin** (`tribunal`) whose `PreToolUse` hook (matcher `*`) adjudicates every tool call through **jev** — TypeSafe AI's typed-decision model. Every tool call gets one of three verdicts mapped to Claude Code's `permissionDecision`:

| jev `choice` | Hook output | Effect |
|---|---|---|
| `allowed` | `allow` | runs, no prompt |
| `rejected` | `deny` + reason | blocked, reason shown to Claude |
| `human_ask` | `ask` | normal human permission prompt |

**Load-bearing invariant: fail-to-human.** Any error (endpoint down, timeout, malformed answer, missing key) falls through to Claude Code's native permission flow via non-blocking exit or explicit `ask`. The hook may only tighten permissions, never loosen them. Never "fix" a failure path into an auto-allow.

## Commands

```bash
python3 -m unittest discover -s tests -v   # full test suite
```

Credentials are **env-only — nothing reads a config file for keys, creds never touch this repo's disk**:
- `TRIBUNAL_PROVIDER` (`hosted` default, or `cloudflare`; legacy `CCV_PROVIDER` accepted)
- Hosted: `TRIBUNAL_API_KEY` (or legacy `JEV_API_KEY`), optional `TRIBUNAL_ENDPOINT` (or legacy `TRIBUNAL_JEV_URL`/`CCV_JEV_URL`)
- Cloudflare: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`

## Architecture

Tiered evaluation, all in one stdlib-only Python script (`hooks/tribunal.py`):

1. **Fast path** — safe-tools list + exact built-in Bash commands (`git status`, `pwd`) → `allow` with zero network. Rules JSON can remove but not add built-in fast-path entries. Never prefix/regex-match Bash into auto-allow.
2. **Jev path** — one POST: `state` (cwd, tool, input) + a single `choice` question whose criteria are the three verdicts. Inputs above 8 KiB go straight to `ask`; never approve based on a truncated view. `answers.verdict.choice` maps via dict lookup; missing/low/invalid confidence → `ask`.
3. **Content screen** — `PreToolUse` and `UserPromptExpansion` screen resolved skill/command files; `PostToolUse` screens `WebFetch` and `WebSearch` results. `TRIBUNAL_SCAN` enables `skills`, `web`, both (the default for unset or invalid values), or `off`. Content is UTF-8 chunked; the worst verdict wins. Clean skill files are content-address cached; unresolved skill names retain the regular tool-call verdict. Web content is warned about, never replaced.

Provider envelopes differ in wrapping — Cloudflare nests `state`+`questions` inside `input` on the request **and** nests the response at `result.result.answers` (live-proven); the `answers.verdict` shape itself is identical, so mapping is provider-independent. Evidence: `docs/research/2026-09-22-prototype-evidence.md`.

Stdlib only (`hashlib`, `json`, `math`, `os`, `re`, `sys`, `time`, `urllib.request`) — no pip deps, no config-file credential path, by decision.

## Where things are

- `hooks/tribunal.py` — main hook script
- `hooks/validator.py` — backwards-compatibility alias for `hooks/tribunal.py`
- `skills/setup-cloudflare/SKILL.md` — setup skill (`/tribunal:setup-cloudflare`)
- `skills/setup-scanning/SKILL.md` — setup skill (`/tribunal:setup-scanning`)
- `docs/plans/2026-09-22-custom-command-validator-design.md` — PRD (historical decisions + rationale)
- `docs/plans/2026-09-22-custom-command-validator.md` — original implementation plan
- `docs/plans/2026-09-30-content-screen-design.md` — content-screen design (spike findings + decisions)
- `docs/plans/2026-09-30-content-screen-plan.md` — content-screen implementation plan
- `docs/research/2026-09-30-content-screen-spike.md` — live-captured hook payload evidence for skills/web
- `docs/research/2026-09-22-research-findings.md` — verified hook contract + jev API facts
- `docs/research/2026-09-22-prototype-evidence.md` — live-captured wire-contract evidence
- `JOURNEY.md` — chronological decision log. **Refresh it before every commit that carries a meaningful change** — the JOURNEY entry lands in the same commit as the change it describes.

## Conventions

- Plugin hook registration uses exec form (`"command": "python3", "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/tribunal.py"]`, `timeout: 30`) — never shell form.
- Verified hook facts worth trusting from research docs: hook `ask` forces the prompt even in auto mode; deny reasons go to Claude, allow/ask reasons to the user only; exit 0 + no stdout = no decision.
- Install route is a marketplace: repo-root `.claude-plugin/marketplace.json` → `/plugin marketplace add heruujoko/claude-tribunal` (or local clone path) → `/plugin install tribunal@claude-tribunal`.
