---
name: setup-cloudflare
description: Configure the tribunal plugin to use Cloudflare Workers AI as its jev provider. Detects the user's OS and shell, shows the exact lines to persist TRIBUNAL_PROVIDER, CLOUDFLARE_ACCOUNT_ID, and CLOUDFLARE_API_TOKEN in the right profile file, and verifies the result without ever exposing the token. Use when the user wants to set up, configure, or troubleshoot Cloudflare credentials for this plugin.
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

    export TRIBUNAL_PROVIDER=cloudflare
    export CLOUDFLARE_ACCOUNT_ID=<account id>
    export CLOUDFLARE_API_TOKEN=<api token>

fish:

    set -gx TRIBUNAL_PROVIDER cloudflare
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
for v in ("TRIBUNAL_PROVIDER", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
    print("{}: {}".format(v, "set" if os.environ.get(v) else "MISSING"))'

All three `set` → done. Any `MISSING` → the profile was not sourced or the
lines were not added; go back to Step 2.

If the variables are `set` in the *current* session but the user skipped the
profile edit, warn: **a new terminal will not inherit them** — persistence
requires Step 2.

## Step 5 — Optional live smoke test

If the plugin repo (or install) is on disk, offer one real verdict request:

    printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"},"cwd":"/tmp"}' \
      | python3 <path-to-plugin>/hooks/tribunal.py

Expected: one JSON line with a `permissionDecision` of `deny` or `ask` and a
reason naming jev. The token appears nowhere in the output. If it fails, the
hook still answers `ask` — the machine is never left unprotected.
