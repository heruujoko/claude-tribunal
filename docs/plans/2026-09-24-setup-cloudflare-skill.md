# Setup-Cloudflare Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bundle a documentation-only `/custom-command-validator:setup-cloudflare` skill that guides a user through persisting the three Cloudflare env vars in their shell profile — without the skill ever touching a credential.

**Architecture:** One new file, `skills/setup-cloudflare/SKILL.md`, following the plugin-skills layout (`<plugin-root>/skills/<name>/SKILL.md` → invoked as `/custom-command-validator:setup-cloudflare`). The skill is instructions for Claude, not code: it detects OS + shell, prints the exact lines to append, and verifies with set/MISSING output only. Plus a README "Initial setup" section. No changes to `hooks/`, no unit tests, no new dependencies.

**Tech Stack:** Markdown with YAML frontmatter; POSIX shell commands the skill tells Claude to run (`uname`, `basename "$SHELL"`, a python3 env check).

**Design doc:** `docs/plans/2026-09-24-setup-cloudflare-skill-design.md`
**Plugin-skills reference:** https://code.claude.com/docs/en/skills (frontmatter `name`/`description`; `${CLAUDE_PLUGIN_ROOT}` available)

---

### Task 1: Create the skill

**Files:**
- Create: `skills/setup-cloudflare/SKILL.md`

**Step 1: Create `skills/setup-cloudflare/SKILL.md`** with exactly this content:

````markdown
---
name: setup-cloudflare
description: Configure the custom-command-validator plugin to use Cloudflare Workers AI as its jev provider. Detects the user's OS and shell, shows the exact lines to persist CCV_PROVIDER, CLOUDFLARE_ACCOUNT_ID, and CLOUDFLARE_API_TOKEN in the right profile file, and verifies the result without ever exposing the token. Use when the user wants to set up, configure, or troubleshoot Cloudflare credentials for this plugin.
---

# Set up the Cloudflare provider

Guide the user through persisting three environment variables. Security rules
for this skill — follow them exactly:

- **Never** ask the user to paste `CLOUDFLARE_API_TOKEN` (or any credential)
  into the chat, a file you write, or a command you run.
- **Never** read, print, copy, or store credential values yourself.
- The user edits their own shell profile; you only show what to add and how to
  verify it.

## Step 1 — Detect platform and shell

Run these and nothing else:

    uname -s
    basename "$SHELL"

- `Darwin` (macOS) or `Linux` → continue.
- Anything else → **STOP**: "This plugin supports macOS and Linux only
  (zsh, bash, or fish)."

Map shell to profile file and syntax:

| Shell | Profile file | Syntax |
|---|---|---|
| zsh | `~/.zshrc` | `export NAME=value` |
| bash on macOS | `~/.bash_profile` | `export NAME=value` |
| bash on Linux | `~/.bashrc` | `export NAME=value` |
| fish | `~/.config/fish/config.fish` | `set -gx NAME value` |

Any other shell → **STOP** with the supported list. Never guess a profile path.

## Step 2 — Show the user what to add

Present the block below (adjusted to their shell/syntax) with placeholders.
State plainly: **the token will be stored in plaintext in the profile file.**

POSIX shells (zsh/bash):

    export CCV_PROVIDER=cloudflare
    export CLOUDFLARE_ACCOUNT_ID=<account id>
    export CLOUDFLARE_API_TOKEN=<api token>

fish:

    set -gx CCV_PROVIDER cloudflare
    set -gx CLOUDFLARE_ACCOUNT_ID <account id>
    set -gx CLOUDFLARE_API_TOKEN <api token>

Tell the user to edit the profile locally, save, and open a **new terminal**.

## Step 3 — Where the values come from

- **Account ID**: Cloudflare dashboard → Workers & Pages → account ID shown in
  the right sidebar. Or `wrangler whoami` if installed.
- **API token**: dashboard → My Profile → API Tokens → Create Token. A token
  with **Workers AI Read** permission is sufficient. Or `wrangler auth token`.

`wrangler` is optional; the dashboard route needs no extra tooling.

## Step 4 — Verify (in a NEW terminal)

Give the user this check — it prints set/MISSING per variable, never values:

    python3 -c 'import os
for v in ("CCV_PROVIDER", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
    print(f"{v}: {'set' if os.environ.get(v) else 'MISSING'}")'

All three `set` → done. Any `MISSING` → the profile was not sourced or the
lines were not added; go back to Step 2.

If the variables are `set` in the *current* session but the user skipped the
profile edit, warn: **a new terminal will not inherit them** — persistence
requires Step 2.

## Step 5 — Optional live smoke test

If the plugin repo (or install) is on disk, offer one real verdict request:

    printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"},"cwd":"/tmp"}' \
      | python3 <path-to-plugin>/hooks/validator.py

Expected: one JSON line with a `permissionDecision` of `deny` or `ask` and a
reason naming jev. The token appears nowhere in the output. If it fails, the
hook still answers `ask` — the machine is never left unprotected.
````

**Step 2: Verify frontmatter and plugin packaging**

Run: `head -4 skills/setup-cloudflare/SKILL.md && claude plugin validate .`
Expected: frontmatter shows `name: setup-cloudflare` and a one-line `description:`; validation output contains `Validation passed`.

**Step 3: Security check — no credential handling**

Run: `grep -nE 'read.*profile|cat ~/|wrangler auth token [>|]' skills/setup-cloudflare/SKILL.md`
Expected: no matches that print or redirect a token (the string `wrangler auth token` alone, listed as a value *source*, is fine; a command that captures or writes it is not).

**Step 4: Commit**

```bash
git add skills/
git commit -m "feat: bundled setup-cloudflare skill (documentation-only, no credential handling)"
```

---

### Task 2: README section + final verification

**Files:**
- Modify: `README.md` (new "Initial setup" section after Installation)

**Step 1: Add to `README.md`**, directly after the Installation section:

````markdown
## Initial setup (Cloudflare provider)

The plugin bundles a setup skill that detects your OS and shell and shows the exact
lines for your profile (`~/.zshrc`, `~/.bash_profile`, `~/.bashrc`, or fish config):

```
/custom-command-validator:setup-cloudflare
```

It sets `CCV_PROVIDER=cloudflare`, `CLOUDFLARE_ACCOUNT_ID`, and
`CLOUDFLARE_API_TOKEN` persistently in your shell profile. The skill never reads,
receives, or writes your token — you edit the profile yourself, and it only verifies
`set`/`MISSING` per variable. Note the token lives in plaintext in the profile.
macOS and Linux only (zsh, bash, fish).
````

**Step 2: Run the full verification set**

```bash
python3 -m unittest discover -s tests -v
claude plugin validate .
```
Expected: `Ran 47 tests ... OK`; `Validation passed`.

**Step 3: Detection sanity on this machine (macOS + zsh)**

Run: `uname -s && basename "$SHELL"`
Expected: `Darwin` and `zsh` → the skill's table maps to `~/.zshrc`, matching this repo's documented default flow.

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README initial-setup section for bundled skill"
```

---

## Final verification (whole plan)

- `claude plugin validate .` → passes (warnings about marketplace description/author are pre-existing and acceptable)
- `python3 -m unittest discover -s tests -v` → 47 passing (unchanged)
- `git log --oneline` shows the two new commits on `feature/implement-validator`
