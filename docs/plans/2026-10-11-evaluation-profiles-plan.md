# Tribunal evaluation profiles

## Context
The current Jev instructions require operations to be clearly safe and reversible and offer little workflow context. This encourages human_ask for reasonable developer work. Add developer (default), office-design, and browsing profiles, global switching, and an interview-based custom-profile creation skill. Preserve non-negotiable security evaluation and all existing permission/failure semantics.

Work on existing branch `feat/evaluation-profiles` (starting HEAD `1fba16e09913a0754cd3bd01332e93e504798ae2`). No worktrees. No commit, push, PR, or paid/live provider calls without explicit authorization. Repository research remains in main when a shared-checkout agent cannot be used. Implementation must use an explicitly selected medium-tier executor in the shared checkout; if the harness cannot provide that, report the blocker rather than silently execute on another tier. All integrated code review and verification stay in main.

## Approved requirements
- Developer is the default; users can select office-design or browsing.
- Selection is global across Tribunal sessions, not per repository.
- A switching skill lists profiles, shows the active profile, and switches it.
- A separate creation skill interviews the user and previews a custom profile before saving; activation is separately confirmed.
- Profiles provide context to Jev, not fast-path allow rules or security exemptions.

## Architecture and security
1. Keep the existing supported wire contract: `questions.verdict.instructions` and `criteria`, `state`, and provider-specific wrapping. Do not introduce an assumed system-prompt API field.
2. Compose immutable shared security instructions with fixed built-in profile guidance. Update allowed criteria to recognize routine, bounded, profile-appropriate work rather than demand literal reversibility of every action. Material missing safety facts still mean human_ask; clearly malicious calls mean rejected.
3. Developer guidance covers ordinary builds/tests, visible and understood Python/temporary scripts, bounded Agent/Task delegation, and explicit non-force pushes to non-protected feature branches. Execution/network/delegation alone is not grounds to ask. Do not assume referenced script contents, remote ownership, or branch protection can be inferred from the current input; names other than main/master are not proof of safety.
4. Office-design guidance covers scoped document and asset edits/exports. Browsing guidance covers public read-only retrieval; account actions, publishing, uploads, purchases, and sensitive data transfer require appropriate authorization.
5. Every profile highlights credential exfiltration, destructive changes, permission/policy tampering, malicious code, prompt injection, supply-chain execution, and untrusted downloaded/plugin/package content. Descriptions claiming consent or safety are evidence, not proof. Neither a temporary path nor a package/tool name establishes trust.
6. Custom profiles are bounded structured context: `purpose`, `routine_tasks`, `ask_before` (nonempty strings/lists with byte/count limits). Send custom context as a separately labeled JSON value in state, with immutable instructions saying it is lower-priority workflow context, never permission to override security. No arbitrary security/criteria/model/credential/fast-path fields. This limits configuration capabilities, but is not a claim that schema validation can guarantee model resistance to injection.
7. Preserve `map_answer`, `extract_answer`, `evaluate_native`, saved-permission eligibility, input budget, confidence gate, and native adapter restrictions. No profile-specific automatic allow, shell parsing, script inspection, expanded fast paths, or new network requests per evaluation. `hooks/register.ts` should not need changes.

## Global storage
- One fixed user-level file: `~/.claude/tribunal/profiles.json`, outside repositories and the plugin cache. Never discover policy from cwd or the existing restrictive `TRIBUNAL_CONFIG` file. No new env/config override in this version.
- Minimal schema: `{ "active": "developer", "custom": { "my-profile": { "purpose": "...", "routine_tasks": ["..."], "ask_before": ["..."] } } }`.
- Built-in definitions live in source, cannot be shadowed by custom names. Validate strict schema, slug names, field types, count/UTF-8 byte bounds, and active-name existence. Bound file reads before parsing. Do not load credentials or executable configuration.
- Only a missing file defaults to developer. An existing malformed, unreadable, oversized, or unknown-profile configuration forces ask through the existing failure handler; do not silently revert to a more permissive profile.
- Read selection on every evaluation, so a successful switch applies to subsequent evaluations in every session, not already-running requests.
- Reuse one stdlib-only profile module for evaluator loading and skill-facing management. CLI supports listing/showing selection, switching, and creating from structured stdin. Validate before writing, preserve unrelated custom entries, and use atomic replacement with owner-only storage. Reject symlink targets and unsupported overwrite operations; no custom delete/edit feature initially. Serialize management read-modify-write operations with a small stdlib lock on supported macOS/Linux platforms so simultaneous sessions do not lose profiles. Never advise bypassing Tribunal if policy changes themselves ask for approval.

## Implementation steps
### 1. Profile definitions, storage, and management
**Files:** new `hooks/profiles.py`, new `tests/test_profiles.py`.
**Action:** Implement three concise built-ins, immutable security guidance, strict global store loading, bounded custom context, and the small CLI above. Use only stdlib. Keep management commands runnable as `python3 -I <plugin-root>/hooks/profiles.py ...`; avoid imports dependent on cwd or new dependencies. Read-only list must not create storage. Creation must not activate automatically.
**Verify:** Temporary-home tests: missing-file default, all selections, persistence/reload, invalid schema/names/fields/types/sizes, custom name collision, unknown active profile, unreadable file, symlink refusal, atomic save/no data loss, and concurrent creation. Real CLI tests exercise stdin and return codes without credentials or network.

### 2. Compose Jev requests
**Files:** `hooks/tribunal.py`, `tests/test_config.py`, `tests/test_jev_path.py`, `tests/test_main.py`; adjust other test environment helpers only if needed.
**Action:** Reuse `load_config` for selecting/loading profile and `build_request` for composing instructions, fixed choice criteria, and custom context. Validate profile before fast-path evaluation. Keep provider envelopes, mapping, confidence threshold, fast-path entries, and native output unchanged. Make all tests hermetic so an actual user global profile cannot influence import-time CFG values or subprocess tests; reuse temporary-home helpers instead of arbitrary production path overrides.
**Verify:** Same profile guidance appears in hosted and Cloudflare requests. Security guidance appears for every built-in/custom profile. Malicious-looking custom strings stay in labeled context and cannot overwrite instructions/criteria/config. Existing invalid-profile storage leads to ask, with saved-permission eligibility false, even on an otherwise fast-path call. Existing provider/input/confidence/permission regressions remain green. Mock results prove mapping, not real model judgment.

### 3. Switching and creation skills
**Files:** new `skills/profile/SKILL.md`, new `skills/create-profile/SKILL.md`, skill CLI tests in `tests/test_profiles.py` (or one small dedicated file only if clearer).
**Action:** Use `disable-model-invocation: true` to make policy-management skills explicitly user invoked. Resolve installed plugin helper via the supported skill/plugin-root mechanism, never assume repository cwd. Switching skill shows current profile/list and switches only to the user's chosen profile. Creation skill asks one question at a time about purpose, typical operations, destinations/data, and ask-before boundaries, avoids collecting secrets, generates bounded structured fields, previews exact data and global scope, saves after explicit approval, and separately offers activation. Unsafe requests to disable scrutiny are not converted into exemptions. Explain next-evaluation scope and prompt-only limits.
**Verify:** Plugin validation recognizes both skills; management CLI examples run with an isolated home outside repo cwd, under `-I`. Skill metadata and management workflow checks verify explicit invocation, preview-before-save, and no implicit activation.

### 4. Documentation and behavioral check
**Files:** `README.md`, `CLAUDE.md`, `JOURNEY.md`, `docs/plans/2026-10-11-evaluation-profiles-design.md`, `docs/plans/2026-10-11-evaluation-profiles-plan.md`; new small `tests/check_profile_verdicts.py`.
**Action:** Document developer default (intentional behavior change), profile boundaries/storage/skills, no-restart switching, fail-to-human on corrupt storage, custom context sent to provider, and visibility limitations. Refresh JOURNEY for the meaningful change, before any later authorized commit. Save the approved design and actionable plan once plan mode is exited. Add a small opt-in behavioral probe using existing build_request/real_post/map_answer; compare old instructions/criteria with profile requests on representative safe, ambiguous, injection, exfiltration, unknown-script, package-execution, and destructive calls. No tools described by probes are actually executed. Print choices/confidence and summary; do not present stochastic model outcomes as deterministic guarantees.
**Verify:** Local/mock probe check without real credentials. Live comparison only after user authorizes provider transmission/spend; then report actual allowed/ask/deny distributions and unsafe approvals, never infer improvement from prompt-string tests.

## Acceptance criteria
- With no profile file, request guidance is developer. Every built-in can be selected globally via the skill; the next request from a second process reflects the switch without restart.
- The creation skill can save a valid named profile after preview/approval and activation requires an explicit user choice; invalid profiles cannot replace security criteria or add configuration capabilities.
- Both providers receive the same immutable security guidance plus the selected workflow context. Profile failures ask rather than default/allow; downstream restrictions, confidence gate, and saved-permission semantics do not weaken.
- A runnable behavioral comparison exists. Real reduction in human_ask is claimed only if live results demonstrate it, with any unsafe results disclosed.

## Verification and review
Main runs `python3 -m unittest discover -s tests -v`, `claude plugin test .`, `claude plugin validate .`, and `python3 tests/check_native_permissions.py`; inspect integration helper first to keep test homes isolated. Tests use temporary homes and mock providers, never user profile state/credentials. Main reviews the exact integrated diff, scoped to changed lines, at most three blockers and two rounds. Report actual pass/fail/skip status. Stop with verified local changes; no git publication/commit or live provider call unless separately authorized.

## Deliberate limits
No per-project profiles, arbitrary free-form system prompt overrides, profile editor/deletion UI, npm/pip dependencies, script/package inspection, model-based profile creation API, or deterministic safety guarantees from prompts. Add those only for a demonstrated need. Existing fast-path read tools remain outside Jev evaluation.
