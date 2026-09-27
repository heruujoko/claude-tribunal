# Setup-Cloudflare Skill — Design

Date: 2026-09-24
Status: Approved (brainstorm session, same day)
Branch: `feature/implement-validator` (extends the implemented plugin)

## Problem

Setting up the Cloudflare provider requires three env vars
(`CCV_PROVIDER=cloudflare`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`).
Users must know their shell's profile file, the correct export syntax, and how to
verify the result without leaking the token. The plugin should teach this, not
just document it.

## Decisions

- **Documentation-only skill.** The skill detects OS + shell and prints
  instructions; the user edits their own profile. The skill never asks for the
  token in chat, never reads profile files, never writes credentials, and never
  runs `wrangler`. It cannot receive a secret, so it cannot leak one.
- **Persistent setup (user choice "1+2").** Guide + persist: the values live in
  the shell profile so every future Claude Code session inherits them. Plaintext
  in the profile is an accepted trade-off, stated to the user during setup.
- **Platform support: macOS and Linux only, shells zsh / bash / fish.** Windows
  and unknown shells get a hard stop with a clear message — never a guessed
  profile path. (bash on macOS → `~/.bash_profile`; bash on Linux → `~/.bashrc`;
  fish → `~/.config/fish/config.fish` with `set -gx` syntax.)

## Skill contract

Invocation: `/custom-command-validator:setup-cloudflare` (bundled at
`skills/setup-cloudflare/SKILL.md`, frontmatter `name: setup-cloudflare`).
The description tells Claude to suggest it when a user mentions configuring
Cloudflare for this plugin.

Flow:
1. Detect OS (`uname`) and shell (`$SHELL` basename). Unsupported → stop with the
   supported list.
2. Show the exact lines to append to the detected profile, with placeholders
   where the user fills real values — and the warning that the profile stores
   the token in plaintext.
3. Point to where the values come from: account ID from the Cloudflare dashboard
   (or `wrangler whoami`); API token from dashboard → My Profile → API Tokens
   (or `wrangler auth token`). Wrangler is optional, not required.
4. After the user edits: a check command that prints `set` / `MISSING` per
   variable (never values) — must run in a **new terminal** so the profile is
   actually sourced.
5. Optional live smoke test: pipe one tool-call payload through
   `hooks/validator.py`; success prints only the verdict choice + confidence.

Failure handling: unsupported OS/shell → explicit stop; session-set-but-not-
persisted vars → warn that new terminals won't inherit them; missing values →
re-point at step 3.

## Non-goals

- Any skill-side handling of the token (interactive prompt, profile writing)
- Windows support
- Changes to `hooks/validator.py`, `hooks.json`, or the test suite

## Testing

Checklist review (no unit tests — the skill is documentation with shell snippets):
- Detection on this machine (macOS + zsh) yields `~/.zshrc` and zsh syntax.
- Check command prints set/MISSING only; verified by running it.
- Smoke test output contains no token material.
- `claude plugin validate .` still passes; README gains a setup section.

## Future work

- A `/setup-hosted` sibling for `JEV_API_KEY` (same shape, smaller)
- Optional machine-specific keychain storage (out of scope; env-only policy holds)
