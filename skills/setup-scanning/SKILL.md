---
name: setup-scanning
description: Configure which content the tribunal plugin screens. Explains the skills and web scopes (both on by default with no config), asks which combination the user wants, shows the exact profile line to set TRIBUNAL_SCAN, and verifies the result. Use when the user wants to enable, disable, or adjust content screening for this plugin.
---

# Set up content screening

Content screening has two scopes, and **both are on by default with no
config**:

| Scope | What it screens | When |
|---|---|---|
| `skills` | Skill/command files before their instructions reach context | PreToolUse Skill and UserPromptExpansion |
| `web` | WebFetch/WebSearch results for prompt injection | PostToolUse |

Cost note: one jev call per web result. Skills are cached by content, so a
clean skill is screened once until it changes.

## Step 1 — Choose the scopes

Ask the user which they want:

| Choice | Effect |
|---|---|
| both (default) | remove any `TRIBUNAL_SCAN` line from the profile |
| skills only | `TRIBUNAL_SCAN=skills` |
| web only | `TRIBUNAL_SCAN=web` |
| off | `TRIBUNAL_SCAN=off` |

## Step 2 — Detect platform and shell

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

## Step 3 — Show the user what to add

Present the one line below (adjusted to their shell/syntax):

POSIX shells (zsh/bash):

    export TRIBUNAL_SCAN=<value>

fish:

    set -gx TRIBUNAL_SCAN <value>

Tell the user to edit the profile locally, save, and open a **new terminal**.
For the default (both scopes), removing any existing `TRIBUNAL_SCAN` line is
enough.

## Step 4 — Verify (in a NEW terminal)

Give the user this check — it prints the effective scope, never anything
sensitive:

    python3 -c 'import os
raw = os.environ.get("TRIBUNAL_SCAN", "").strip().lower()
parts = {p.strip() for p in raw.split(",") if p.strip()}
print("scanning:", "off" if raw == "off" else ",".join(sorted(parts)) if parts and parts <= {"skills", "web"} else "skills,web")'

The output should match the chosen scope. If it does not, the profile was not
sourced or the line was not added; go back to Step 3.
