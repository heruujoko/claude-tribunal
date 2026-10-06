# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code **plugin** (`tribunal`) whose native `classic.PreToolUse` adapter adjudicates tool calls through **jev** — TypeSafe AI's typed-decision model. Requires mod-capable Claude Code (terminal v2.1.287+, tested v2.1.289). Calls already restricted by downstream hooks keep that restriction. Jev verdicts map to Claude Code's permission decisions:

| jev `choice` | Hook output | Effect |
|---|---|---|
| `allowed` | `allow` | runs, no prompt |
| `rejected` | `deny` + reason | blocked, reason shown to Claude |
| `human_ask` | `ask` | normal human permission prompt |

**Load-bearing invariant: fail-to-human.** Any error (endpoint down, timeout, malformed answer, missing key) falls through to Claude Code's native permission flow via non-blocking exit or explicit `ask`. The hook may only tighten permissions, never loosen them. Never "fix" a failure path into an auto-allow.

## Commands

```bash
python3 -m unittest discover -s tests -v   # Python regressions
claude plugin test .                       # native adapter regressions
claude plugin validate .
python3 tests/check_native_permissions.py  # real engine, local mock providers
```

Credentials are **env-only — nothing reads a config file for keys, creds never touch this repo's disk**:
- `TRIBUNAL_PROVIDER` (`hosted` default, or `cloudflare`; legacy `CCV_PROVIDER` accepted)
- Hosted: `TRIBUNAL_API_KEY` (or legacy `JEV_API_KEY`), optional `TRIBUNAL_ENDPOINT` (or legacy `TRIBUNAL_JEV_URL`/`CCV_JEV_URL`)
- Cloudflare: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`

## Architecture

Tiered evaluation in a stdlib-only Python script (`hooks/tribunal.py`), invoked by the thin native adapter (`hooks/register.ts`):

1. **Fast path** — safe-tools list + exact built-in Bash commands (`git status`, `pwd`) → `allow` with zero network. Rules JSON can remove but not add built-in fast-path entries. Never prefix/regex-match Bash into auto-allow.
2. **Jev path** — one POST: `state` (cwd, tool, input) + a single `choice` question whose criteria are the three verdicts. Inputs above 8 KiB go straight to `ask`; never approve based on a truncated view. `answers.verdict.choice` maps via dict lookup; missing/low/invalid confidence → `ask`.

For a valid, sufficiently confident `human_ask` only, the adapter queries `$.tool.check` on the full effective input (including downstream rewrites). An `allow` with a nonempty explicit matching `rule` removes Tribunal's ask and defers to native permissions. No mode-only consent, approval cache, settings parsing, or settings writes. Failures and low-confidence asks are never eligible. Preserve other hooks' asks/denials and context. Adapter/process/query failures force `ask`; module-load failures cannot run that fallback, so loading must be verified.

The integration fixture uses normal model-initiated calls: plugin-origin `$.tool.call` deliberately discards permission updates in v2.1.289, so it cannot prove approval persistence. Actual interactive dialogs remain outside the automated check.

Provider envelopes differ in wrapping — Cloudflare nests `state`+`questions` inside `input` on the request **and** nests the response at `result.result.answers` (live-proven); the `answers.verdict` shape itself is identical, so mapping is provider-independent. Evidence: `docs/research/2026-09-22-prototype-evidence.md`.

Stdlib only (`json`, `os`, `re`, `sys`, `urllib.request`) — no pip deps, no config-file credential path, by decision.

## Where things are

- `hooks/register.ts` — native permission-aware adapter (automatic registration)
- `hooks/tribunal.py` — Python evaluator; `--native` includes ask eligibility, default retains classic JSON
- `hooks/validator.py` — backwards-compatibility alias for `hooks/tribunal.py`
- `skills/setup-cloudflare/SKILL.md` — setup skill (`/tribunal:setup-cloudflare`)
- `docs/plans/2026-09-22-custom-command-validator-design.md` — PRD (historical decisions + rationale)
- `docs/plans/2026-09-22-custom-command-validator.md` — original implementation plan
- `docs/research/2026-09-22-research-findings.md` — verified hook contract + jev API facts
- `docs/research/2026-09-22-prototype-evidence.md` — live-captured wire-contract evidence
- `JOURNEY.md` — chronological decision log. **Refresh it before every commit that carries a meaningful change** — the JOURNEY entry lands in the same commit as the change it describes.

## Conventions

- Automatic registration is `{"modules": ["./register.ts"]}` in `hooks/hooks.json`, an explicit exception to the original Python-only registration. Invoke Python via `$.process.run` with an argument vector and 30-second timeout, never a shell. Do not also register the classic Python hook (duplicate adjudication). Older clients cannot run automatic Tribunal protection; direct classic invocation remains compatible but cannot respect saved permissions.
- Verified hook facts worth trusting from research docs: hook `ask` forces the prompt even in auto mode; deny reasons go to Claude, allow/ask reasons to the user only; exit 0 + no stdout = no decision.
- Install route is a marketplace: repo-root `.claude-plugin/marketplace.json` → `/plugin marketplace add heruujoko/claude-tribunal` (or local clone path) → `/plugin install tribunal@claude-tribunal`.
