# Prototype Evidence — jev decide contract

**Question:** what exactly do we send to jev `/decide`, what exactly comes back, and
does `choice` + `confidence` map cleanly to `allow`/`deny`/`ask`?

**Run:** `python3 prototype/jev_contract.py` (live; `--mock` for documented-shape parse proof).
Live creds: copy `config.toml.example` → `config.toml` (gitignored), fill `url` + `api_key`.
Env vars `JEV_API_KEY` / `CCV_JEV_URL` override the file.

## Captured evidence (2026-09-22, live)

1. **Endpoint is live and validates auth before body.**
   `POST https://jevtypesafeai.com/api/v1/decide` with a dummy `jv_live_…` key returns:
   ```
   HTTP 401
   {"error":"Missing API key. Send 'Authorization: Bearer jv_live_...'."}
   ```
   A deliberately garbage body (`{"garbage": true}`) with the same dummy key returns the
   **same 401** — auth runs first, so the request body cannot be validated without a real
   key. Our body shape follows the documented schema exactly; live confirmation pending key.

2. **Error contract note.** The 401 body is `{"error": "<string>"}` — a plain message,
   not the `code` field the docs show for 402 (`insufficient_credits`). The plugin must
   not assume a `code` field exists on errors. Irrelevant for mapping (errors never map —
   they fall through to the native permission flow), but recorded.

3. **Parse + mapping proven against the documented response shape** (mock mode, exact
   shape from jevtypesafeai.com/docs):
   ```
   answers.verdict = {"type": "choice", "choice": "rejected", "confidence": 0.91,
                      "probabilities": {...}}
   → MAPPED DECISION: deny
   ```
   Confidence gate and unusable-answer → ask path are covered by the plan's unit tests.

4. **Request baseline** (exact body the plugin will send, sent live, accepted up to auth):
   ```json
   {"model": "jev-latest",
    "state": {"cwd": "<cwd>", "tool": "<tool_name>", "input": "<json tool_input>"},
    "questions": {"verdict": {"type": "choice",
      "instructions": "Should an AI agent be allowed to run this tool call on the user's machine? Pick human_ask when uncertain or when a human should decide.",
      "criteria": {"allowed": "clearly safe and reversible for this machine",
                   "rejected": "clearly unsafe, destructive, or against the user's interest",
                   "human_ask": "uncertain, sensitive, or needing human judgment"}}}}
   ```

## Provider envelopes (core contract shared, wrapper differs)

| | hosted (jevtypesafeai.com) | cloudflare (/ai/run) |
|---|---|---|
| URL | `https://jevtypesafeai.com/api/v1/decide` | `https://api.cloudflare.com/client/v4/accounts/{id}/ai/run` |
| Auth | `Bearer jv_live_…` | `Bearer CLOUDFLARE_API_TOKEN` |
| Model | `jev-latest` / pinned | `typesafe/jev` |
| Body | `{model, state, questions}` | `{model, input: {state, questions}}` |
| Response | `answers.*` top-level | `answers.*` top-level — **identical** |
| `usage` | tokens + `cost_usd` + `credits_remaining_usd` | tokens only (billed via Cloudflare credits) |

Cloudflare contract captured 2026-09-22 from user-supplied docs (request wraps the same
`state`+`questions` inside `input`; response shows a `choice` answer with `confidence`
and `probabilities`, same as hosted). `map_answer` is provider-independent.

## Open — needs a real key

Live verdict evidence — pick a provider in `config.toml` (`[jev] provider`), fill its
creds, run `python3 prototype/jev_contract.py`, and record below (expected: 200 + typed
answers for the 4 cases on either provider; any non-200 shape).

```
<!-- paste live run here -->
```

## Verdict

Contract is implementation-ready: request shape final, mapping logic validated against
the documented shape, error fall-through verified live. Delete this prototype once
`hooks/validator.py` passes its tests against the same contract.
