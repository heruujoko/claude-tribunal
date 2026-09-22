# Custom Command Validator — PRD & Design

Date: 2026-09-22
Status: Approved + revised (research findings, same day — see Changes)

## Problem

Claude Code's auto mode decides tool-call permissions with Anthropic's own classifier.
This project replaces that judgment with **jev** — TypeSafe AI's typed-decision model —
running on a **provider of our choosing** (hosted jevtypesafeai.com key, official
TypeSafe console, or a gateway), so permission decisions run on our endpoint, our rules,
our cost profile.

## Goal

A Claude Code plugin that intercepts **every tool call** before execution and asks jev
for one of exactly three verdicts:

| Verdict | Behavior in Claude Code |
|---|---|
| `allowed` | `permissionDecision: allow` — runs, no prompt |
| `rejected` | `permissionDecision: deny` — blocked, reason fed back to Claude |
| `human_ask` | `permissionDecision: ask` — routed to the normal human permission prompt |

## Decisions (2026-09-22, post-research)

- **Jev only.** No generic OpenAI chat-completions backend. Output format is jev's typed
  Decision API, not parsed prose.
- **Provider freedom via URL.** The plugin POSTs to `CCV_JEV_URL` (any jev decide
  endpoint: hosted `/api/v1/decide`, official `/v1/systemone`, gateway route).
- **Portable question shape.** A custom `choice` question (`allowed`/`rejected`/
  `human_ask` criteria) rather than the hosted-only `agent/risk` shortcut, so every
  provider works identically.
- **Confidence gate.** jev returns a calibrated `confidence`; below `CCV_MIN_CONFIDENCE`
  the verdict becomes `human_ask`.

## Non-goals (v1)

- OpenAI-spec generic backend (dropped by decision above)
- Verdict caching
- Sending conversation/transcript context to the validator
- Marketplace publishing (installed via local marketplace)

## Functional requirements

1. `PreToolUse` hook registered for all tools (`matcher: "*"`), exec form with
   `${CLAUDE_PLUGIN_ROOT}` path placeholder.
2. **Tiered evaluation**:
   - Fast path: configurable safe-tools list and safe-Bash-command regex list → `allow`
     without any network call.
   - Jev path: everything else → one `POST {CCV_JEV_URL}` decide call.
3. **Jev request**: `{model, state: {cwd, tool, input (truncated ~8 KB)}, questions:
   {verdict: choice(allowed|rejected|human_ask)}}` — tool call only, no transcript.
4. **Verdict mapping**: `answers.verdict.choice` → allow/deny/ask.
   `confidence < CCV_MIN_CONFIDENCE` → `ask`. Unusable/missing answer → `ask`.
   There is no free-text parsing — the answer type is fixed by the request.
5. Fail-to-human: unreachable endpoint, timeout, non-200, or missing API key → fall
   through to Claude Code's native permission flow (hook exits non-blocking). The hook
   may only tighten permissions, never loosen them. (Verified against live docs:
   hook `ask` forces the prompt even in auto mode.)
6. Plugin packaging (`.claude-plugin/plugin.json` + local marketplace manifest),
   installed via `/plugin marketplace add <repo>` + `/plugin install`.

## Non-functional requirements

- Python 3 stdlib only — no pip dependencies, no node_modules.
- Zero latency on fast-path calls; one small round trip otherwise (jev: 70–500 ms,
  $0.42/M input tokens, output free).
- Default timeout 10 s.

## Architecture

```
tool call → hooks/validator.py
              ├─ fast path: safe tool / safe command rules → allow
              └─ jev path: POST {CCV_JEV_URL}  {model, state, questions.verdict}
                            → answers.verdict: {choice, confidence}
                            → allow | deny | ask  (low confidence → ask)
```

### Plugin layout

```
.claude-plugin/plugin.json       # plugin manifest
.claude-plugin/marketplace.json  # local marketplace for install
hooks/hooks.json                 # PreToolUse registration, matcher "*", exec form
hooks/validator.py               # all logic
config.example.json              # safe-tools / safe-commands example rules
```

### Verdict mapping

| jev says | Hook outputs | Claude Code does |
|---|---|---|
| `choice: allowed` (confidence ≥ min) | `permissionDecision: allow` | executes without prompting |
| `choice: rejected` (confidence ≥ min) | `permissionDecision: deny` + reason | blocks; reason shown to Claude |
| `choice: human_ask`, or low confidence, or unusable answer | `permissionDecision: ask` | shows the normal permission prompt |

### Error handling

| Situation | Behavior |
|---|---|
| Endpoint unreachable / timeout / non-200 | non-blocking exit → native permission flow |
| Missing/invalid answer shape | `ask` |
| `CCV_API_KEY` unset | `ask` |
| validator.py crashes | non-blocking exit → native permission flow unchanged |

### Configuration

Environment variables:

| Var | Purpose | Default |
|---|---|---|
| `CCV_JEV_URL` | jev decide endpoint (any provider) | `https://jevtypesafeai.com/api/v1/decide` |
| `CCV_API_KEY` | Bearer key (`jv_live_…`) | required for jev path |
| `CCV_MODEL` | `jev-latest` or pinned (e.g. `jev-1.13.0`) | `jev-latest` |
| `CCV_TIMEOUT` | Request timeout (seconds) | `10` |
| `CCV_MIN_CONFIDENCE` | Below this → `ask` | `0.5` |
| `CCV_CONFIG` | Path to JSON rules file | plugin dir `config.json` |

Rules file defaults: safe tools = Read, Glob, Grep, TodoWrite, task tools; safe Bash
commands = minimal read-only regex list (`git status|diff|log`, `ls`, `cat`, …),
user-extendable.

## Testing

One `unittest` file per area (stdlib, endpoint mocked via `unittest.mock`):

- Verdict mapping: choice → allow/deny/ask; confidence gate; unusable answer → ask
- Fast-path rules hit and miss (no network on hit)
- Decide request shape: state contents, truncation, model
- `real_post`: URL, auth header, timeout, answer extraction; errors propagate
- Hook contract via subprocess: control JSON on stdout, exit codes, fail-to-human

Manual E2E: install the plugin, run a session, observe verdicts per outcome.

## Risks

- **Provider/API drift**: jev launched Sept 2026; the decide API is young. Pin
  `CCV_MODEL` in production so thresholds don't shift; endpoint URL is configurable.
- **Sway via tool input**: state still contains tool-input text that could try to steer
  the choice. Mitigated by fixed criteria labels and the confidence gate — far smaller
  surface than free-text JSON verdict parsing.
- **Latency** on non-fast-path calls: one small round trip; jev is 70–500 ms.

## Future work

- Verdict cache for repeated identical (tool, input) pairs
- Optional transcript context in `state`
- Per-project rule overrides
- Hosted `agent/risk` shortcut (adds risk score + categories) behind a config flag
