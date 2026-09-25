# Claude Custom Command Validator

A Claude Code plugin whose `PreToolUse` hook (matcher `*`) routes every tool call through **jev** — TypeSafe AI's typed-decision model — to classify each action as allowed, rejected, or requiring human approval.

## Verdict Mapping

| jev `choice` | Hook output | Effect |
|---|---|---|
| `allowed` | `allow` | Runs without prompting |
| `rejected` | `deny` + reason | Blocked; reason shown to Claude |
| `human_ask` | `ask` | Normal human permission prompt |

Evaluations operate on two transports:
- **Hosted**: `POST` to `CCV_JEV_URL` (default: `https://jevtypesafeai.com/api/v1/decide`).
- **Cloudflare**: `POST` to Cloudflare Workers AI (`https://api.cloudflare.com/client/v4/accounts/{account}/ai/run`).

A deterministic fast path automatically allows read-only tools and exact safe commands with zero network calls.

## Installation

Install from a local clone using the plugin marketplace:

```bash
/plugin marketplace add /path/to/claude-custom-command-validator
/plugin install custom-command-validator@local-dev
```

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

## Environment Variables & Configuration

Credentials are env-only — they are never read from disk.

| Variable | Description | Default |
|---|---|---|
| `CCV_PROVIDER` | Provider backend (`hosted` or `cloudflare`) | `hosted` |
| `CCV_JEV_URL` | Jev decide endpoint URL (hosted provider) | `https://jevtypesafeai.com/api/v1/decide` |
| `JEV_API_KEY` | API key for hosted jev endpoint | `""` |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID (required for `cloudflare` provider) | `""` |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token (for `cloudflare` provider) | `""` |
| `CCV_MODEL` | Decision model | `jev-latest` (`typesafe/jev` for Cloudflare) |
| `CCV_TIMEOUT` | Request timeout in seconds | `10` |
| `CCV_MIN_CONFIDENCE` | Minimum confidence threshold (`0.0` to `1.0`) below which verdicts fall back to `ask` | `0.5` |
| `CCV_CONFIG` | Path to custom rules JSON file | `${PLUGIN_ROOT}/config.json` |

## Fast-Path Rules File

An optional JSON rules file (`config.json` or path in `CCV_CONFIG`) can customize fast-path rules (see `config.example.json`):

```json
{
  "safe_tools": ["Read", "Glob", "Grep", "TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"],
  "safe_commands": ["git status", "pwd"]
}
```

**Replace semantics:**
- The rules file may replace only `safe_tools` and `safe_commands`.
- Credentials and provider settings remain env-only and cannot be specified in the rules file.
- `safe_commands` and `safe_tools` may only contain subsets of the built-in defaults (removing entries to tighten permissions); they cannot add arbitrary shell commands or tools.

## Hook Semantics & Nuances

- **Fail-to-human**: Any unexpected crash, missing API key, transport error, or malformed response falls through to human confirmation (`ask` or non-blocking exit), never auto-allow.
- **Auto mode override**: A hook decision of `ask` forces a human prompt even in Claude Code's auto mode.
- **Interactive tools**: `allow` cannot auto-approve interactive tools like `AskUserQuestion` or `ExitPlanMode`.
- **Reason visibility**: Deny reasons are shown to Claude to guide tool adjustments; allow and ask reasons are shown to the user only.

## Running Tests

Run the test suite using Python 3 stdlib `unittest`:

```bash
python3 -m unittest discover -s tests -v
```
