# Claude Tribunal (`tribunal`)

> Multi-verdict SLM decision engine and tool adjudicator for Claude Code.

Tribunal is a Claude Code plugin whose `PreToolUse` hook intercepts every tool call and evaluates it against **jev** — TypeSafe AI's typed-decision model. 

Like the Living Tribunal's three-faced judgment, every action is weighed into one of three explicit verdicts:

| Verdict (`choice`) | Hook Decision | Effect |
|---|---|---|
| `allowed` | `allow` | Safe and reversible; runs without prompting |
| `rejected` | `deny` + reason | Unsafe or destructive; blocked with explanation returned to Claude |
| `human_ask` | `ask` | Sensitive or uncertain; defers to human confirmation |

---

## How It Works

Tribunal operates in two evaluation tiers:

1. **Fast Path (0 ms, 0 network):** Safe read-only inspection tools (`Read`, `Glob`, `Grep`, Task tools) and exact harmless shell commands (`git status`, `pwd`) are immediately approved locally without making a network call.
2. **Jev SLM Path:** Any tool call outside the fast path is dispatched to a fast small language model (`jev`) on your configured provider (Hosted or Cloudflare Workers AI) with structured evaluation criteria. The model's typed answer is mapped directly to Claude Code's permission system.

### Respecting Saved Permissions

A sufficiently confident Jev `human_ask` does not prompt again when Claude Code's native permission checker returns **allow with a matching explicit rule**. This includes saved permissions (such as “Yes, and don't ask again”) and explicit session rules, within the scope and lifetime Claude Code assigns them. A one-time Yes creates no reusable Tribunal permission.

Tribunal still evaluates the call: Jev rejection, low confidence, provider failure, and input-budget failures cannot be bypassed by a saved rule. Mode-only approval and built-in read-only approval are not saved consent. Other hooks' asks/denials and native deny/ask rules remain effective. Tribunal does not parse settings, cache approvals, or infer consent from successful execution.

### Core Invariant: Fail-to-Human

Tribunal is designed around strict defensive defaults:
* **Fail-to-Human:** If an API token is missing, the endpoint is unreachable, an envelope is malformed, or model confidence falls below the threshold, Tribunal falls back to `ask`. It **never** fails open into an auto-allow.
* **Auto Mode Override:** In Claude Code auto mode, a hook decision of `ask` forces an interactive confirmation prompt.
* **Input Bounds:** Inputs exceeding 8 KiB bypass SLM evaluation and require human review directly.

---

## Installation

**Requires Python 3 and mod-capable Claude Code: terminal v2.1.287+ (tested on v2.1.289), or Desktop Code tab engine v2.1.286+.** Automatic adjudication uses a native function-hook adapter around the stdlib-only Python evaluator. Older clients cannot load this registration and therefore have **no automatic Tribunal protection**; upgrade before using it.

Module-load failure happens before the adapter's fail-to-human handler can run. For a clone, run `claude plugin validate /path/to/claude-tribunal`; expect `./register.ts` with `classic.PreToolUse`. After installing/reloading, use `claude --debug` to confirm the Tribunal hooks module loaded. Validation alone does not prove it loaded in your session.

Direct invocation of `python3 hooks/tribunal.py` (and the legacy `hooks/validator.py` alias) retains the classic JSON contract for custom command-hook setups, but cannot inspect native permissions and still repeats `human_ask` prompts. Do not register it alongside the module: that would adjudicate twice.

### For External Testers (Direct from GitHub)

Install directly into Claude Code with two simple commands:

```bash
# 1. Add the Tribunal marketplace from GitHub
/plugin marketplace add heruujoko/claude-tribunal

# 2. Install the tribunal plugin
/plugin install tribunal@claude-tribunal
```

*(After installation, restart Claude Code or run `/reload-plugins` to load the hook and skill).*

### For Local Development

If you are developing locally or testing changes from a clone:

```bash
# 1. Register your local clone as a marketplace
/plugin marketplace add /path/to/claude-tribunal

# 2. Install the plugin from the local marketplace
/plugin install tribunal@claude-tribunal
```

---

## Configuration

Credentials are **environment-only** — they are never read from disk or stored in configuration files.

### Option A: Cloudflare Workers AI (Recommended)

Run the bundled setup skill inside Claude Code:

```bash
/tribunal:setup-cloudflare
```

The skill detects your OS and shell (zsh, bash, or fish), provides the exact export commands to add to your shell profile, and verifies the environment without ever reading or exposing your secret token.

Required environment variables:
* `TRIBUNAL_PROVIDER=cloudflare`
* `CLOUDFLARE_ACCOUNT_ID=<your-account-id>`
* `CLOUDFLARE_API_TOKEN=<your-api-token-with-workers-ai-read>`

### Option B: Hosted Decision Endpoint

To use the hosted decision endpoint:

```bash
export TRIBUNAL_PROVIDER=hosted
export TRIBUNAL_API_KEY=<your-api-key>
# Optional: override default endpoint (https://jevtypesafeai.com/api/v1/decide)
# export TRIBUNAL_ENDPOINT=https://your-endpoint/v1/decide
```

---

## Environment Variables Reference

| Variable | Description | Default |
|---|---|---|
| `TRIBUNAL_PROVIDER` | Provider backend (`hosted` or `cloudflare`) | `hosted` |
| `TRIBUNAL_ENDPOINT` | Decision endpoint URL (hosted provider) | `https://jevtypesafeai.com/api/v1/decide` |
| `TRIBUNAL_API_KEY` | API key for decision endpoint (legacy `JEV_API_KEY` also supported) | `""` |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID (required for `cloudflare` provider) | `""` |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token (for `cloudflare` provider) | `""` |
| `TRIBUNAL_MODEL` | Decision model ID | `jev-latest` (`typesafe/jev` for Cloudflare) |
| `TRIBUNAL_TIMEOUT` | Request timeout in seconds | `10` |
| `TRIBUNAL_MIN_CONFIDENCE` | Minimum confidence threshold (`0.0` to `1.0`) below which verdicts fall back to `ask` | `0.5` |
| `TRIBUNAL_CONFIG` | Path to custom rules JSON file | `${PLUGIN_ROOT}/config.json` |

*(Note: Legacy `TRIBUNAL_JEV_URL`, `JEV_API_KEY`, and `CCV_*` environment variables remain supported for backwards compatibility.)*

---

## Fast-Path Customization (Optional)

You can customize the local fast path by providing a `config.json` (or pointing `TRIBUNAL_CONFIG` to a JSON file). See `config.example.json`:

```json
{
  "safe_tools": ["Read", "Glob", "Grep", "TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"],
  "safe_commands": ["git status", "pwd"]
}
```

* **Restrictive only:** You may remove built-in tools or commands to tighten restrictions, but you cannot introduce arbitrary auto-allowed commands through this file.
* **Credentials forbidden:** The rules file cannot define tokens, accounts, or providers.

---

## Running Tests

The Python evaluator uses only the standard library; the TypeScript adapter uses Claude Code's built-in API. No pip or npm dependencies are required.

```bash
python3 -m unittest discover -s tests -v
claude plugin test .
claude plugin validate .
python3 tests/check_native_permissions.py
```

The integration check requires Claude Code v2.1.289+ and runs normal model-initiated calls against local mock model/Jev endpoints in a temporary project, without real provider credentials or spend. It checks saved-rule scope, compound calls, deny/ask precedence, session expiry, one-time approval, local persistence, and rule removal. PermissionRequest hooks simulate approval responses; actual interactive “Yes” dialogs are not covered.
