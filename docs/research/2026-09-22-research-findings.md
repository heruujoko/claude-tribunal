# Research Findings — Hook Contract & Jev Model

Date: 2026-09-22 · Branch: `research/hook-contract`
Sources: code.claude.com/docs/en/hooks.md, plugins-reference.md, plugin-marketplaces.md, discover-plugins.md (fetched live); jevtypesafeai.com (/get-jev, /docs)

Status: hook-contract subagent died on infra error; verification re-run directly against live docs.

## A. Claude Code hook contract — verified against live docs

| # | Plan assumption | Verdict |
|---|---|---|
| 1 | stdin: `tool_name`, `tool_input`, `hook_event_name`, `cwd`, `session_id`, … | **CONFIRMED** (also receives `tool_use_id`, `permission_mode`) |
| 2 | Output `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": …, "permissionDecisionReason": …}}` | **CONFIRMED** exactly |
| 3 | `permissionDecision` values `allow`/`deny`/`ask` | **CONFIRMED**, plus a 4th value `"defer"` (exit gracefully, resume later) — we ignore it |
| 4 | Exit 0 silent = no decision, normal permission flow; exit 2 = deny (stderr shown to Claude); other nonzero = non-blocking, normal flow | **CONFIRMED** — "The hook can deny the call, but staying silent doesn't approve it" |
| 5 | `hooks/hooks.json` shape, `matcher: "*"` matches all tools, per-hook `timeout` in seconds | **CONFIRMED**. Note: command-hook timeout **defaults to 600s** — our explicit `30` is correct |
| 6 | `${CLAUDE_PLUGIN_ROOT}` expands in plugin hook commands | **CONFIRMED** |
| 7 | `.claude-plugin/plugin.json` manifest | **CONFIRMED** |
| 8 | Local install | **CORRECTED**: via a local marketplace — repo-root `.claude-plugin/marketplace.json` listing the plugin with `"source": "."`, then `/plugin marketplace add ./repo` and `/plugin install <name>@<marketplace>` |

### Gotchas we did not assume (all matter)

- **Reason routing**: `permissionDecisionReason` for `deny` is shown **to Claude**; for `allow`/`ask` shown **to the user only**. Our deny-reason design is correct; don't expect Claude to see allow/ask reasons.
- **Hook `ask` beats auto mode**: a hook's `ask` forces the permission prompt even in auto mode — the built-in classifier can still deny but cannot silently approve past our ask. Our `human_ask` is always honored.
- **`allow` is not absolute**: it skips the prompt except for actions no mode auto-approves; `AskUserQuestion`/`ExitPlanMode` need `updatedInput` paired with `allow`. Harmless for us (those tools are safe-listed or routed to ask anyway) — worth a README note.
- **Deny/ask permission rules still evaluated regardless of hook output** — native rules compose with, and can tighten past, our allow.
- **Multiple PreToolUse hooks**: precedence `deny` > `defer` > `ask` > `allow`.
- **Exec form is preferred** for hook commands referencing path placeholders: `"command": "python3", "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/validator.py"]` — no shell quoting edge cases. Plan should switch from shell form.
- **`if` field** can pre-filter handler spawning without running the script — not needed for our all-tools matcher, noted for future.

### Plan amendments required

1. `hooks/hooks.json`: use exec form (`command` + `args`), keep `timeout: 30`.
2. README install section: local-marketplace route (marketplace.json + the two commands above).
3. Document reason-visibility and allow-limitation nuances in README.

## B. Jev model — providers and response format

**What it is**: TypeSafe AI's "System One" model — takes unstructured `state` + typed `questions`, returns calibrated **typed answers** (choice / score / yes-no probability). No prose, no JSON parsing, "0 hallucinations by construction". 70–500ms. Launched Sept 2026.

**Cost**: $0.42 per **million input tokens**, **output tokens free** (~$0.00003 per small tool call, ~$0.0013 for a maxed 8KB payload).

**Providers** (fastest → most official):
1. Hosted API at jevtypesafeai.com — `jv_live_…` key, prepaid, instant. **The ready-made endpoints live here.**
2. Gateways: Vercel AI Gateway (`typesafe-ai/jev`), OpenRouter (`typesafe/jev`, decisions endpoint), Cloudflare AI Gateway.
3. Official TypeSafe console (`console.typesafe.ai`) — raw `/v1/systemone`.
4. Ecosystem: `jev-mcp` (npx, Claude Code), `langchain-typesafe`.

**Core API**: `POST https://jevtypesafeai.com/api/v1/decide`, Bearer auth, body `{model?, state, questions}` where each question is `choice` (labelled options → winner + probabilities + confidence), `score` (ordered levels → fractional score), or `noul` (yes/no → calibrated 0–1). Response: `{model, answers: {<name>: <typed answer>}, usage: {input_tokens, cost_usd, credits_remaining_usd}}`.

**Purpose-built for us**: `POST /api/v1/agent/risk` — "Gate a proposed tool call":
- request `{"goal", "tool", "arguments", "context"}`
- response `{"action": "allow"|"confirm"|"block", "risk": 0–1, "categories": [...], "confidence": 0–1}`

Mapping to our verdicts: `allow`→allowed, `confirm`→human_ask, `block`→rejected — **exact 1:1**, no parsing layer needed. `confidence` gives a free safety knob (low confidence → human_ask).

**Caveat**: jevtypesafeai.com is an independent developer platform, not TypeSafe AI itself. Official `/v1/systemone` and gateway routes expose the raw decide API, not the ready-made `agent/risk` shortcut — a custom `choice` question reproduces the same verdict on any provider.

## Design impact — RESOLVED by user decision, same day

**Jev only; provider freedom via configurable endpoint URL.** The generic OpenAI-spec
backend is dropped. The plugin POSTs a custom `choice` question (`allowed`/`rejected`/
`human_ask` criteria) to `CCV_JEV_URL` — the portable decide shape that every provider
(hosted, official `/v1/systemone`, gateways) speaks. `answers.verdict.confidence` becomes
a safety knob (`CCV_MIN_CONFIDENCE`, below → `human_ask`). The hosted-only `agent/risk`
shortcut is future work. PRD and implementation plan revised accordingly on this branch.
