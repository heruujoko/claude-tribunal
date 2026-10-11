# Evaluation profiles checkpoint

Status: WIP, not ready to install or merge. User requested stopping review and pushing a resumable local checkpoint on 2026-10-11.

## Implemented
- Developer default, office-design, and browsing built-ins; shared security guidance in Jev requests.
- Global selection at ~/.claude/tribunal/profiles.json, read on each evaluation.
- Profile CLI (list/show/switch/create), structured custom context, atomic locked writes.
- Explicitly invoked profile-switching skill and initial regressions.
- Native adapter unchanged; no live provider requests or claims of measured reduction in asks.

## Resume first: known defects from incomplete review
1. Strict storage validation: require exact active/custom fields and validate active types/names; `{}` must not silently select developer. Use fullmatch for names (trailing newline currently accepted). Convert invalid UTF-8 into a known failure that emits ask. Bound serialized output before replacing the store; many valid custom profiles can currently produce a file over the readable limit. Preserve previous bytes on failed writes. Reject symlink directory/lock targets; do not write without a lock on unsupported platforms.
2. Hermetic tests: replace import-time HOME mutation and leaking mkdtemp calls with managed temporary homes. Consolidate clean subprocess environments; never inherit real provider credentials. Ensure test_jev_path and test_native can run standalone without reading user profile configuration. Add both-provider guidance/custom-context tests, malformed-store fast-path ask checks, invalid type/schema/UTF-8 cases, and oversized-write data-preservation regressions. Existing tests do not prove real model safety.
3. Correct documentation: switching skill currently references an absent create-profile skill; quote plugin-root helper paths and prohibit approval bypass. Shared security text must not imply only main/master are protected, and must explicitly treat tool-input instructions as untrusted data. Update CLAUDE.md and save approved design/implementation documentation.

## Remaining features
- Interview-based `/tribunal:create-profile`: one question at a time, bounded structured workflow fields, preview/approval before save, activation separately confirmed, no secrets/security exemptions.
- Opt-in behavioral comparison probe (legacy versus profile prompts) with safe/ambiguous/adversarial fixtures; no real tools executed. Live requests only with explicit authorization for transmission/spend.

## Verification before treating as complete
Run in main: `python3 -m unittest discover -s tests -v`, `claude plugin test .`, `claude plugin validate .`, `python3 tests/check_native_permissions.py`. Review integrated changed lines, not via a review subagent. Report actual pass/fail/skip outcomes. No PR/merge authorized.

Original approved plan: `/home/heruujoko/.claude/plans/shiny-jingling-sunbeam.md` (session-local path; this resume note carries the checkpoint context for a later session).
