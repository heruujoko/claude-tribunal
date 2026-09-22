# JOURNEY.md

The project's timeline: what we decided, how we discovered things, and how we build.
Chronological, newest at the bottom. One entry per event, the decision and the why.

**How we build** (the loop this project follows):
brainstorm → PRD/design doc → research (evidence over assumption) → prototype
(evidence-based baseline) → plan (TDD tasks) → implement → self-review in main thread →
commit per step. Artifacts live in `docs/plans/`, `docs/research/`, `prototype/`, and
this file. Prototype before building; verify contracts live before trusting docs;
keep every revision traceable to a dated entry here.

---

## 2026-09-22 — Genesis day

**1. The idea.** User asked for a Claude Code plugin that behaves like auto mode —
validating every command Claude wants to run on the machine — but with a **custom model
and endpoint** so judgment runs on our choice of AI, not Anthropic's. The validation
contract is exactly three outcomes: `allowed`, `rejected`, `human_ask`. Git initialized;
PRD written first (`docs/plans/2026-09-22-custom-command-validator-design.md`).

**2. Scope decision.** Validator intercepts **all tool calls**, not just Bash — a full
auto-mode replacement, matching the project name only in spirit.

**3. Safety decision (load-bearing).** **Fail-to-human**: endpoint unreachable, timeout,
or garbage response → fall back to Claude Code's normal permission prompt. The hook may
only tighten permissions, never loosen them. Every later design choice inherits this.

**4. Architecture decision.** **Tiered**: a deterministic fast path (safe-tools list +
safe-Bash-command regexes) allows the boring 80% with zero cost/latency; the model judges
only the risky rest. Verdict caching deferred (YAGNI).

**5. Runtime decision.** Python 3 **stdlib only** — no pip, no node_modules, runs
anywhere. Plugin packaging (`.claude-plugin/` + `hooks/hooks.json`) for `/plugin` install.

**6. Plan + license.** Implementation plan written TDD-first (7 tasks, 28 tests,
complete code in-plan: `docs/plans/2026-09-22-custom-command-validator.md`). MIT license
added. Repo pushed to `github.com/heruujoko/claude-custom-auto-mode`.

**7. Research phase (branch `research/hook-contract`).** Lesson in method: the research
subagent and WebFetch both died on infra errors → **fell back to curl in the main
thread** and verified the hook contract against live docs ourselves. Discovery is
evidence-based or it didn't happen.

**8. Hook contract verified (live docs).** Control JSON shape, exec-form hooks (no shell
quoting), per-hook `timeout` in seconds (docs default 600 — we set 30), local-marketplace
install route, and two gems: a hook `ask` **forces the prompt even in auto mode**, and
deny reasons go to Claude while allow/ask reasons show only to the user.
`docs/research/2026-09-22-research-findings.md`.

**9. The jev discovery.** jev (TypeSafe AI) is **not** an OpenAI chat model — it's a
typed Decision API: send `state` + typed `questions`, get calibrated typed answers.
No prose, no parsing, "0 hallucinations by construction". 70–500ms, $0.42/M input
tokens, output free. Its ready-made `agent/risk` endpoint returns
`allow|confirm|block` — a 1:1 match for our three outcomes.

**10. The pivot (user decision).** **Jev only; provider freedom via URL.** The generic
OpenAI-spec backend was dropped. Portable custom `choice` question (criteria =
allowed/rejected/human_ask) instead of the hosted-only `agent/risk` shortcut, so any
provider works (hosted key, official `/v1/systemone`, gateways). Bonus: `confidence`
became a safety knob — below `CCV_MIN_CONFIDENCE` → `human_ask`. PRD and plan revised
in place.

**11. Prototype first (this is how we build).** Before implementing, a throwaway
prototype proved the wire contract against the **live** endpoint:
`prototype/jev_contract.py` + `prototype/EVIDENCE.md`. Captured: the 401 error contract,
auth-runs-before-body-validation, and parse+map proven against the documented response.
Live verdicts pending a real API key. Baseline recorded; prototype deleted once the
real implementation passes its tests.

**12. Credentials for live tests.** `config.toml.example` committed; `config.toml`
(gitignored, user-filled) holds the real provider `url` + `api_key` + `model`. The
prototype reads it via stdlib `tomllib` (Python 3.13) — env vars still override. Keys
never enter git.

**13. Cloudflare provider contract (user-supplied docs).** The "one decide shape
everywhere" assumption was corrected: Cloudflare's `/ai/run` wraps `state`+`questions`
inside `input`, uses model id `typesafe/jev`, and auths with a Cloudflare token — but
`answers.*` is identical, so the mapping layer stays provider-independent. `usage` lacks
cost fields there (billing = Cloudflare credits). Prototype now speaks both envelopes
(`[jev] provider` in config.toml); evidence table added to EVIDENCE.md.

**14. Pre-token security pass.** Before real credentials landed in `config.toml`, a
full-repo review found no vulnerabilities and three leak-path hygiene gaps — all fixed
in one commit: `.env`/`.env.*` gitignored (env-var creds are a documented interface,
wrangler creates `.env` files), prototype output now redacts the key if a server ever
echoes it (paste-into-EVIDENCE path), inline "never fill this file" warnings on
`config.toml.example` cred lines, `chmod 600 config.toml`. Safe-to-fill verdict given.

**15. CLAUDE.md + the JOURNEY-before-commit rule.** Repo guidance for future Claude
instances created: the fail-to-human invariant, commands, provider model, doc map.
New convention adopted at the same time (user decision): **a commit that changes
behavior without a JOURNEY entry is incomplete** — the entry lands in the same commit
as the change it describes. This entry is the first under that rule.

**Next (unwritten):** live-key verdict evidence → implement the plan → self-review →
first working plugin install.
