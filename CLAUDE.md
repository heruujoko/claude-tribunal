# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code **plugin** whose `PreToolUse` hook (matcher `*`) replaces auto mode's permission judgment with **jev** — TypeSafe AI's typed-decision model. Every tool call gets one of three verdicts mapped to Claude Code's `permissionDecision`:

| jev `choice` | Hook output | Effect |
|---|---|---|
| `allowed` | `allow` | runs, no prompt |
| `rejected` | `deny` + reason | blocked, reason shown to Claude |
| `human_ask` | `ask` | normal human permission prompt |

**Load-bearing invariant: fail-to-human.** Any error (endpoint down, timeout, malformed answer, missing key) falls through to Claude Code's native permission flow via non-blocking exit. The hook may only tighten permissions, never loosen them. Never "fix" a failure path into an auto-allow.

## Commands

```bash
python3 -m unittest discover -s tests -v   # full test suite
```

Credentials are **env-only — nothing reads a config file for keys, creds never touch this repo's disk**: `CCV_PROVIDER` (`hosted` default, or `cloudflare`), `JEV_API_KEY`/`CCV_JEV_URL` for hosted, `CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN` for cloudflare.

## Architecture

Tiered evaluation, all in one stdlib-only Python script (`hooks/validator.py`, per plan):

1. **Fast path** — safe-tools list + exact built-in Bash commands (`git status`, `pwd`) → `allow` with zero network. Rules JSON can remove but not add built-in fast-path entries. Never prefix/regex-match Bash into auto-allow.
2. **Jev path** — one POST: `state` (cwd, tool, input) + a single `choice` question whose criteria are the three verdicts. Inputs above 8 KiB go straight to `ask`; never approve based on a truncated view. `answers.verdict.choice` maps via dict lookup; missing/low/invalid confidence → `ask`.

Provider envelopes differ in wrapping — Cloudflare nests `state`+`questions` inside `input` on the request **and** nests the response at `result.result.answers` (live-proven); the `answers.verdict` shape itself is identical, so mapping is provider-independent. Evidence: `docs/research/2026-09-22-prototype-evidence.md` (live-captured responses, verdicts, and per-call cost).

Stdlib only (`json`, `os`, `re`, `sys`, `urllib.request`) — no pip deps, no config-file credential path, by decision.

## Where things are

- `docs/plans/2026-09-22-custom-command-validator-design.md` — PRD (decisions + rationale)
- `docs/plans/2026-09-22-custom-command-validator.md` — **implementation plan: 7 TDD tasks with complete code, execute task-by-task**
- `docs/research/2026-09-22-research-findings.md` — verified hook contract + jev API facts (source of truth for hook behavior; don't re-derive from memory)
- `docs/research/2026-09-22-prototype-evidence.md` — live-captured wire-contract evidence (retired prototype's baseline)
- `JOURNEY.md` — chronological decision log. **Refresh it before every commit that carries a meaningful change** — the JOURNEY entry lands in the same commit as the change it describes. A commit that changes behavior without a JOURNEY entry is incomplete.

## Conventions

- Implementation status: plugin implemented and tested (47 tests); prototype retired, its evidence preserved under `docs/research/`.
- Plugin hook registration uses exec form (`"command": "python3", "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/validator.py"]`, `timeout: 30`) — never shell form.
- Verified hook facts worth trusting from research docs: hook `ask` forces the prompt even in auto mode; deny reasons go to Claude, allow/ask reasons to the user only; exit 0 + no stdout = no decision.
- Install route is a local marketplace: repo-root `.claude-plugin/marketplace.json` → `/plugin marketplace add <repo>` → `/plugin install`.
