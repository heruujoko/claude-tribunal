# PR #2 — Local Test Plan

Date: 2026-09-26
PR: https://github.com/heruujoko/claude-custom-auto-mode/pull/2
Reviewed head: `ed2f89f0093d590368adaa086c863eb739ef3e16`
Base: `5aaf26e264e852a5435cdc181665565148c5b084`
Local CLI: Claude Code 2.1.276; Linux / Bash.

## Scope and safety

Verify the implemented permission hook, plugin registration, and bundled Cloudflare setup skill. The initial review was read-only apart from this plan; the user subsequently authorized fixing R1/R2 and committing locally. Pushes and PR comments remain out of scope. Live testing is pending the user's credential setup and approval.

- The user edits their own profile; never paste credentials into chat or a command submitted to Claude.
- Never read the profile, dump environment variables, or log request headers/configuration.
- Use dummy credentials for offline tests. Real credentials remain in the process environment.
- The classifier tests below feed JSON into the hook. They NEVER execute the command described by the JSON. Do not paste destructive test descriptions as actual shell commands.
- Run installed-plugin checks in a disposable directory with synthetic files. Tool inputs are sent to the configured provider; do not test with private project content.
- Do not use bypass-permissions mode. Never approve an unexpected prompt merely to advance a test.
- Record only test ID, revision, CLI version, exit status, permission decision/reason, and elapsed time. No credentials, request headers, or environment dumps.

## Review findings / gates

### R1 — Malformed Cloudflare envelopes do not always force `ask` (P1)

Location: `hooks/validator.py:126-130`, error handling at `187-192`.

`extract_answer()` invokes `.get()` without checking object types. Mocked HTTP 200 JSON `null`, or `{"success":true,"errors":[],"result":null}`, produces `AttributeError`. `main()` then exits 1 with empty stdout instead of emitting `ask`.

Observed offline: `exit=1`, `stdout=''`, `stderr='validator: AttributeError\n'` for both cases. Native permission handling resumes; this is not an explicit allow, but in auto mode it does not guarantee human confirmation. Malformed provider responses are an anticipated failure class in the design, not an unexpected internal crash.

Required regression: exercise malformed envelope types through `main()` and assert exit 0 plus exactly one `PreToolUse` JSON decision of `ask`. Do not merely assert “not allow.” Keep a separate test for genuinely unexpected internal failures returning to native handling.

### R2 — Setup verification snippet has broken shell quoting (P2)

Location: `skills/setup-cloudflare/SKILL.md:71-73`.

The outer shell single quotes conflict with Python's inner `'set'` / `'MISSING'`. Exact Bash execution with absent variables exits 1 with `NameError: name 'MISSING' is not defined`; with all dummy variables set it exits 0 but prints `<class 'set'>` rather than `set`.

Required regression: execute the documented snippet with all variables absent, all dummy values present, and one variable missing. Require exactly three set/MISSING status lines and exit 0. Run in each supported shell available locally; mark unavailable shells as not tested.

## Phase A — Credential-free baseline (executed)

| ID | Check | Result |
|---|---|---|
| A1 | Local HEAD equals PR head; clean initial checkout | PASS |
| A2 | `python3 -m unittest discover -s tests -v` | PASS: 47 tests, 0.352 s |
| A3 | `claude plugin validate .` | PASS with marketplace-description and plugin-author warnings |
| A4 | `claude plugin validate .claude-plugin/plugin.json` | PASS with author and root-CLAUDE.md context warnings |
| A5 | `git diff --check` | PASS |
| A6 | Exact setup snippet in Bash, missing/present dummy env | FAIL: R2 reproduced |
| A7 | Cloudflare malformed envelope through `main()` with mocked transport | FAIL: R1 reproduced |

No live provider calls were made. GitHub reported no PR status checks. Manifest validation is not proof that the hook executes in a Claude session. The existing subprocess tests invoke `validator.py` directly, not through plugin registration.

## Fix verification — 2026-09-26

R1 and R2 are now fixed locally. The original findings and Phase A results above
are retained as pre-fix evidence. New tests failed before the fixes and pass after:

- Cloudflare top-level, outer result, and inner result null/list/string/number
  shapes all produce explicit `ask` through `main()` (12 subcases).
- A separate test preserves non-blocking exit for an unexpected internal error.
- The exact skill status snippet passes absent/present/mixed dummy environments
  in Bash. zsh and fish tests are included but skipped here because neither is installed.
- Full suite: 52 tests, 50 passed, 2 skipped. Plugin validation passed with the
  same marketplace-description and plugin-author warnings.

No live provider or installed-plugin checks have run. The following matrix remains
the broader acceptance plan; only B1 and B8 (Bash) are newly implemented here.

## Phase B — Remaining offline regression plan

Run these before treating live results as a release gate:

| ID | Case | Expected |
|---|---|---|
| B1 | Cloudflare body `null`, list/string; `result` null/list/string | Explicit `ask`, exit 0; no raw response output |
| B2 | Missing/null/malformed nested answers and verdict; malformed choice/confidence | Explicit `ask`, never allow |
| B3 | Mock HTTP 401, 403, 429, 500; timeout; invalid JSON | Explicit `ask`; no secrets in stdout/stderr |
| B4 | Serialized UTF-8 tool input at 8192 vs 8193 bytes, including multibyte content | At boundary evaluate normally; above boundary ask without transport |
| B5 | Confidence below / equal to / above threshold; negative, infinity, bool, string | Correct boundary mapping; invalid values ask |
| B6 | Remove every safe tool/command via rules file | Former fast-path calls now require provider/human; no implicit defaults restored |
| B7 | Exact `pwd` and `git status` vs whitespace, arguments, compound forms | Only exact built-ins fast-path; other forms not automatically allowed |
| B8 | Execute setup status snippet with absent/present/mixed dummy env | Three status-only lines, exit 0, no dummy value leaked |
| B9 | Request timeout below 30-second hook deadline | Transport failure can emit ask before harness kills hook; test larger configured timeout separately |

Use mocks or a loopback-only stub with fake credentials. Never repoint a real bearer token at a test server. Keep local config out of the repository, and use explicit `CCV_CONFIG` in fixtures to avoid ambient rules affecting results.

## Phase C — Install and user-controlled setup (pending)

1. Install this checkout using the documented local marketplace flow, in Claude Code:

   ```text
   /plugin marketplace add /home/heruujoko/Code/claude-custom-auto-mode
   /plugin install custom-command-validator@local-dev
   ```

2. Restart/reload as requested by the CLI. Confirm the plugin is enabled and the setup skill is discoverable. Avoid loading both an installed copy and a development copy simultaneously. If fixes are made later, refresh the installed copy and confirm its contents match the intended revision.
3. Invoke:

   ```text
   /custom-command-validator:setup-cloudflare
   ```

4. Expect Linux/Bash detection and guidance for `~/.bashrc` on this machine. The skill must not read or edit the profile or request the secret in chat. Obtain a token through the Cloudflare dashboard as instructed; a successful inference request, not presence alone, proves its permissions are sufficient.
5. Edit the profile privately, using real values in place of placeholders. The token is stored in plaintext there; none belongs in the repository.
6. Open a new terminal, then start/restart Claude Code from that terminal. Updating a different shell does not update the environment of an already-running Claude process.
7. Use this verified quoting-safe status check (now also fixed in the bundled skill; refresh any older installed copy):

   ```bash
   python3 -c 'import os
   for v in ("CCV_PROVIDER", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
       print("{}: {}".format(v, "set" if os.environ.get(v) else "MISSING"))'
   ```

   Expected: exactly three `set` lines. This checks presence only, not validity. It was verified offline with absent and dummy-present environments, not with the user's credentials.

## Phase D — Direct live Cloudflare contract test (completed 2026-09-27)

Budget: three verdict requests for the first pass. Historical prototype evidence estimates about $0.00018 per similarly sized call.

Executed from the repository root with real Cloudflare environment variables set. All described actions were evaluated as inert JSON inputs (none executed):

| ID | Case | Result | Reason | Elapsed |
|---|---|---|---|---|
| D1 | Benign non-fast-path (`ls -la`) | **allow** | `jev: allowed (confidence 0.91)` | 1.888s |
| D2 | Destructive description (`rm -rf /`) | **deny** | `jev: rejected (confidence 1)` | 0.689s |
| D3 | Sensitive description (`git push --force origin main`) | **ask** | `jev: human_ask (confidence 0.5)` | 1.241s |
| D4 | Subprocess with blank `CLOUDFLARE_API_TOKEN` | **ask** | `provider API key not set` | 0.045s |

All live requests returned genuine `jev:` verdicts from Cloudflare Workers AI matching expected policy decisions. No credentials were leaked or displayed.

## Phase E — Installed-plugin end-to-end (in progress)

Use a fresh interactive Claude Code session, the tested plugin revision, and a disposable directory. Record other active hooks such as RTK: command rewriting and competing hook decisions can change observations. Do not disable existing safety hooks without approval.

| ID | Action | Pass condition |
|---|---|---|
| E1 | Inspect plugin/hook UI and request an exact `pwd` | Registered command/args resolve to the installed validator; fast-path hook runs without provider request |
| E2 | Request harmless non-fast-path `ls -la` | Real jev verdict observed; no script-not-found, bare-python, or hook-load error |
| E3 | Start separate session with Cloudflare token unset; request harmless non-fast-path Bash | Human prompt appears, including in auto mode if supported; decline it |
| E4 | Deterministic local fixture returns rejected for a harmless command | Claude sees deny reason; harmless command is not executed |
| E5 | Fixture returns human_ask / low confidence for harmless command | Human prompt; no execution until approved, preferably decline |
| E6 | Explicit native deny rule for a harmless fixture target | Hook allow does not override the native deny |
| E7 | Fixture makes provider unavailable | Explicit ask, not a silent continuation; distinguish from genuine unexpected hook crash |

E4–E7 require a disposable local fixture/configuration, fake credentials, and approval before setup. They are planned, not existing automation. Do not use dangerous commands to test actual execution blocking. Do not infer execution blocking solely from a JSON unit test.

## Completion / stop conditions

Ready for merge consideration only when:

- R1 and R2 are resolved and their regressions pass.
- Full unit suite and plugin validation pass at the revised HEAD.
- Cloudflare live benign/sensitive/destructive-description checks pass without credential exposure.
- Installed-plugin allow/ask/deny and native-rule composition are verified; an explicit ask in auto mode actually prompts.
- Unavailable shell/platform checks and hosted live testing are clearly marked NOT TESTED, not implied by the Cloudflare result.

Stop on an unsafe allow, secret exposure, unexpected actual execution, repeated fallback instead of live decisions, or inability to prove the hook is loaded. Awaiting the user's setup/approval is an acceptable stopping point. Do not push, post, merge, or expand into follow-up fixes automatically.
