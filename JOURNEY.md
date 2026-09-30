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

**16. Env-only credentials (user decision, prototype scope).** `config.toml` and its
example were deleted — the prototype reads **only env vars** (`CCV_PROVIDER`,
`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `JEV_API_KEY`, `CCV_JEV_URL`), so real
credentials never exist on this repo's disk at all. Supersedes entries 12–14's
config-file interface; the security posture improves from "gitignored file" to
"no file".

**17. Live evidence day (the payoff of prototype-first).** First live run through
Cloudflare (`/ai/run`, model `typesafe/jev`, HTTP 200 × 4) disproved the doc-shaped
assumption: the real response nests `answers` at `result.result` inside a
`{result, success, errors}` envelope — the prototype caught it by failing safe instead
of mis-parsing. `extract_answer()` now unwraps both envelopes, verified against the
exact captured payloads. Verdict quality on real cases: `git status`→allow (0.99),
`curl|sh`→deny (0.99), force-push→ask (0.55), `/etc/hosts` write→ask with confidence
0.37 — **the confidence gate caught a genuinely ambiguous call before the mapping did**.
Measured cost: ~415 input tokens ≈ $0.00018/verdict. EVIDENCE.md closed; plan and PRD
updated with the envelope contract (+4 tests, now 32).

**18. Codex review day: the plan was the bug.** Two external reviews ran on the branch.
Security pass (second round): clean, merge-safe, no credential leaks. Codex rescue:
"do not merge yet" — and it was right. Four plan defects, all real after verification:
(1) the Bash fast path used start-anchored regexes, so `git status; rm -rf /` would have
been auto-allowed — the exact violation of the fail-safe invariant the project exists
to enforce; (2) `JEV_API_KEY` (prototype, live-tested, user's shell) vs `CCV_API_KEY`
(plan) drift; (3) `CCV_PROVIDER=typo` and missing Cloudflare account silently proceeded;
(4) test-count arithmetic drifted from the listed tests. Fixes, all plan-level before
any code exists: exact-string fast path restricted to built-ins (`git status`, `pwd`),
rules file may only remove entries; `JEV_API_KEY` wins as the live-tested name; strict
config validation with explicit `ask` for invalid provider/numerics/rules; Cloudflare
responses must be `success: true` + `errors: []` + `state: "Completed"` before any
verdict; confidence must be a finite number in [0, 1]; non-fast-path inputs over 8 KiB
ask instead of truncating (a truncated view could hide a dangerous suffix — stricter
than the review asked); counts machine-recounted (47) and a `--self-check` mode added
to the prototype asserting the fail-safe paths. Pushback recorded: prototype's
`git status` live verdict critique noted but moot for the wire-contract evidence.

## 2026-09-24 — First implementation

**19. Research merged, implementation isolated on a branch.** PR #1 merged into
`main` at `5aaf26e`; `feature/implement-validator` began from that commit. The
approved seven-task plan was executed test-first in seven commits. The Python stdlib
hook now registers for every `PreToolUse` event, permits only the reviewed fast-path
entries without network, sends other eligible calls to hosted jev or Cloudflare, and
maps a typed answer to `allow`, `deny`, or `ask`. Missing credentials, oversized input,
invalid configuration, failed transport, bad provider envelopes, and unusable/low-
confidence answers cannot become auto-allow.

**20. Main-thread verification and prototype retirement.** The executor reported 47
passing tests; a separate main-thread run confirmed 47/47. Direct hook smoke checks
confirmed `Read`→`allow` and `git status; rm -rf /`→`ask` when no model key is set.
`claude plugin validate .` passed with two non-blocking metadata warnings (marketplace
description and plugin author). The throwaway prototype was removed, as promised from
day one; its live Cloudflare response and verdict baseline was moved to
`docs/research/2026-09-22-prototype-evidence.md`. One deliberate correction to the
plan's sample code: malformed stdin exits non-blocking before config evaluation, as
the plan's own subprocess test required. No live provider call was made during this
implementation verification; network integration remains to be checked on install.

## 2026-09-24 — Setup skill design

**21. Bundled setup skill (user request, same branch).** "Help users set the
Cloudflare keys by invoking a skill provided by the plugin." Design decision after
clarification: documentation-only skill at `skills/setup-cloudflare/SKILL.md` —
detects OS + shell (macOS/Linux; zsh/bash/fish; Windows unsupported), prints the
exact profile lines with placeholders, and verifies with set/MISSING output only.
Combined behavior "1+2": guide plus persistence in the user's own shell profile;
the skill never sees the token, so it cannot leak it. Plaintext-in-profile
trade-off is stated during setup. No hook or test changes.

**22. Setup skill implemented.** `skills/setup-cloudflare/SKILL.md` landed in two
commits (6097dcf, e3aab9f): `/custom-command-validator:setup-cloudflare` detects
macOS/Linux + zsh/bash/fish, prints the exact profile lines with placeholders,
points at the Cloudflare dashboard (wrangler optional), and verifies set/MISSING
only — Claude executing the skill can never receive the token. Main-thread
verification: 47 tests OK, `claude plugin validate` passed (same two pre-existing
metadata warnings), content reviewed verbatim against the plan, grep for
credential-capture commands clean.

## 2026-09-26 — PR #2 review fixes

**23. Two reproduced regressions fixed before live setup.** Main-thread review of
PR #2 found that malformed Cloudflare JSON (`null` or a non-object `result`)
raised `AttributeError` and resumed native permissions rather than forcing `ask`.
Explicit envelope type checks now route those responses through the existing
known-error path. Regression coverage exercises twelve malformed envelope shapes
through `main()` and separately preserves non-blocking behavior for genuinely
unexpected internal failures.

The bundled setup check also mixed shell and Python single quotes: missing vars
raised `NameError`, while present vars printed `<class 'set'>`. Its status output
now uses shell-safe quoting. Tests extract the actual skill snippet and execute
absent, present, and mixed dummy environments without inheriting credentials.
Both defects were reproduced by failing tests before the fixes. Main-thread final
verification: 52 tests, 50 passed and 2 skipped (zsh/fish unavailable); marketplace
validation passed with the same two metadata warnings. No live provider calls or
credentials were used. The requested subagent implementation used the prescribed
main-thread fallback because the available Agent tool requires isolation, contrary
to this project's shared-checkout-only policy.

**24. Local acceptance plan retained.**
`docs/plans/2026-09-26-pr-2-local-test-plan.md` records the original review evidence,
regression results, private credential setup, bounded live classification, and
installed-plugin checks. Direct Python tests do not prove hook registration or
actual prompt/deny behavior inside Claude Code. Live tests remain pending.

## 2026-09-27 — Live Cloudflare verification

**25. Live Cloudflare contract tests passed.** The user completed setup via the
bundled skill. Direct hook classification checks against Cloudflare Workers AI
(`typesafe/jev`) succeeded on all three test cases with inert JSON inputs:
- Benign command (`ls -la`): returned `allow` (`jev: allowed (confidence 0.91)`).
- Destructive command (`rm -rf /`): returned `deny` (`jev: rejected (confidence 1)`).
- Sensitive command (`git push --force origin main`): returned `ask` (`jev: human_ask (confidence 0.5)`).
- Blank token check: confirmed fail-safe `ask` (`provider API key not set`).
Zero credential material was printed or logged. Phase D of the local test plan is
complete and verified live.

**Next:** verify end-to-end hook interception inside Claude Code sessions.

## 2026-09-28 — Project Evolution: Renamed to Tribunal

**26. Identity and scope evolution.** The project evolved from a command validator
into **Tribunal** (`claude-tribunal`, plugin ID `tribunal`). The name reflects the
Living Tribunal's three-faced judgment, mapping directly to the three typed verdicts
rendered by jev (`allowed` → `allow`, `rejected` → `deny`, `human_ask` → `ask`). It
also establishes the foundation for future expansions where the parent session can
convene the Tribunal to offload open-ended structured decisions to the SLM.

**27. Implementation & backwards compatibility.**
- Hook script created as `hooks/tribunal.py`. An import wrapper in `hooks/validator.py`
  preserves backward compatibility.
- Environment variable configuration now prefers `TRIBUNAL_*` (`TRIBUNAL_PROVIDER`,
  `TRIBUNAL_ENDPOINT`, `TRIBUNAL_API_KEY`, `TRIBUNAL_MODEL`, `TRIBUNAL_TIMEOUT`,
  `TRIBUNAL_MIN_CONFIDENCE`, `TRIBUNAL_CONFIG`) — generalizing away from JEV-specific
  naming to support any future decision backend — while retaining seamless fallback
  to legacy `TRIBUNAL_JEV_URL`, `JEV_API_KEY`, and `CCV_*` variables.
- Plugin manifest (`.claude-plugin/plugin.json`) and marketplace manifest
  (`.claude-plugin/marketplace.json`) now register under plugin name `tribunal`.
- Skill updated to `tribunal:setup-cloudflare` referencing `TRIBUNAL_PROVIDER` and
  `hooks/tribunal.py`.
- Documentation (`README.md`, `CLAUDE.md`) refreshed, keeping user guidance strictly
  focused on currently supported functionality.
- Test suite updated to 55 unit tests (53 passed, 2 skipped due to optional shells),
  covering new `TRIBUNAL_*` env handling, precedence over `CCV_*`, and legacy wrapper execution.


## 2026-09-30 — Content screen: spike and design (issue #5)

**28. Spike before design.** Four hook facts were undocumented, so headless `claude -p`
sessions with a throwaway `--settings` file captured real payloads (global settings never
touched). Findings (`docs/research/2026-09-30-content-screen-spike.md`): `Skill` input is the
name only (`plugin:skill` for plugins), PostToolUse on `Skill` carries no body,
`UserPromptExpansion` carries no expanded text but its `decision: block` works, and
PostToolUse `additionalContext` does reach Claude. Consequence: skills are screened from the
file on disk in PreToolUse / UserPromptExpansion; web results are warned about, not replaced.

**29. Design decisions** (`docs/plans/2026-09-30-content-screen-design.md`): default-on via
`TRIBUNAL_SCAN` (unset or invalid → both scopes, `off` → none); reuse the live-proven `choice`
verdict shape instead of `noul`; chunk instead of truncate (worst chunk wins); cache only
clean skill verdicts, keyed by content; an unresolvable skill keeps today's name-only verdict.

**30. Implementation.** The seven TDD tasks landed in seven commits. Tribunal now resolves
and screens on-disk user, project, and plugin skill files for `PreToolUse` and
`UserPromptExpansion`; clean results use a content-addressed cache, while rejected or uncertain
content is always re-screened. `PostToolUse` warns rather than replaces `WebFetch` and
`WebSearch` results, preserving original content while instructing Claude to treat it as
untrusted. A new `/tribunal:setup-scanning` skill explains default-on scopes, per-result web
cost, content-cached skill cost, shell persistence, and verification. The fail-to-human
invariant applies throughout: malformed verdicts, missing keys, and bounded-screen failures
cannot allow unreviewed content.
