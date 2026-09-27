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
- **Provider-specific transport.** Hosted jev uses `CCV_JEV_URL` (default `/api/v1/decide`);
  Cloudflare uses its account-scoped `/ai/run` URL. Both share the typed `choice` question,
  but the request and response envelopes differ. `JEV_API_KEY` is the hosted key name,
  matching the live-tested prototype.
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
   - Fast path: configurable safe-tools list and **exact** safe-Bash-command list →
     `allow` without any network call. Compound commands, arguments not on the list,
     and shell metacharacters reach jev; they never inherit a safe prefix's verdict.
   - Jev path: everything else → one POST to the selected provider's endpoint.
3. **Jev request**: `{model, state: {cwd, tool, input}, questions:
   {verdict: choice(allowed|rejected|human_ask)}}` — tool call only, no transcript.
   Non-fast-path inputs over 8 KiB of UTF-8 JSON go to `ask` without a model call;
   never classify a truncated view that could hide a dangerous suffix.
4. **Verdict mapping**: `answers.verdict.choice` → allow/deny/ask.
   `confidence < CCV_MIN_CONFIDENCE` → `ask`. Unusable/missing answer → `ask`.
   There is no free-text parsing — the answer type is fixed by the request.
5. Fail-to-human: unreachable endpoint, timeout, non-200, invalid provider/config,
   missing credentials, failed Cloudflare status, or unusable answer → explicit `ask`
   when possible. Unexpected hook crashes exit non-blocking and leave Claude Code's
   native permission flow in charge. The hook must never emit `allow` for a failure.
   (Verified against live docs: hook `ask` forces the prompt even in auto mode.)
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
| Endpoint unreachable / timeout / non-200 | `ask` when caught; unexpected crash → native flow |
| Missing/invalid answer shape or unsuccessful Cloudflare envelope | `ask` |
| Missing `JEV_API_KEY` or Cloudflare account/token | `ask` before network |
| Invalid provider, numeric setting, or rules file | `ask` before network |
| validator.py crashes unexpectedly | non-blocking exit → native flow unchanged |

### Configuration

Environment variables:

| Var | Purpose | Default |
|---|---|---|
| `CCV_PROVIDER` | `hosted` or `cloudflare` | `hosted` |
| `CCV_JEV_URL` | jev decide endpoint (hosted route) | `https://jevtypesafeai.com/api/v1/decide` |
| `JEV_API_KEY` | Bearer key (`jv_live_…`, hosted route) | required for hosted calls |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare route: derives `/ai/run` URL | — |
| `CLOUDFLARE_API_TOKEN` | Cloudflare route auth | — |
| `CCV_MODEL` | Model id (cloudflare default: `typesafe/jev`) | `jev-latest` |
| `CCV_TIMEOUT` | Request timeout (seconds) | `10` |
| `CCV_MIN_CONFIDENCE` | Below this → `ask` | `0.5` |
| `CCV_CONFIG` | Path to JSON rules file | plugin dir `config.json` |

Credentials are env-only — no config file holds keys (decision 2026-09-22). Provider
envelopes: cloudflare wraps the request in `input` and nests the response at
`result.result` (live-proven, `docs/research/2026-09-22-prototype-evidence.md`); verdict mapping is
provider-independent.

Rules file defaults: safe tools = Read, Glob, Grep, TodoWrite, task tools; safe Bash
commands = only exact `git status` and `pwd`. The rules file may only remove built-in
fast-path tool/command entries. Adding any auto-allow requires a reviewed code change;
exact strings alone cannot make arbitrary commands safe. Regex/prefix matching must
never auto-allow a command suffix.

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
