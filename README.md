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

Tribunal operates in three evaluation tiers:

1. **Fast Path (0 ms, 0 network):** Safe read-only inspection tools (`Read`, `Glob`, `Grep`, Task tools) and exact harmless shell commands (`git status`, `pwd`) are immediately approved locally without making a network call.
2. **Jev SLM Path:** Any tool call outside the fast path is dispatched to a fast small language model (`jev`) on your configured provider (Hosted or Cloudflare Workers AI) with structured evaluation criteria. The model's typed answer is mapped directly to Claude Code's permission system.
3. **Content Screen:** Screens skill files and web results independently of tool-call adjudication. Its verdict can block a skill, require confirmation, or warn Claude that a web result is untrusted.

### Core Invariant: Fail-to-Human

Tribunal is designed around strict defensive defaults:
* **Fail-to-Human:** If an API token is missing, the endpoint is unreachable, an envelope is malformed, or model confidence falls below the threshold, Tribunal falls back to `ask`. It **never** fails open into an auto-allow.
* **Auto Mode Override:** In Claude Code auto mode, a hook decision of `ask` forces an interactive confirmation prompt.
* **Input Bounds:** Inputs exceeding 8 KiB bypass SLM evaluation and require human review directly.

---

## Content Screening

Tribunal screens prompt content and tool outputs across three hook events:

- **Skills (`PreToolUse` on `Skill` & `UserPromptExpansion`):** Screens the backing `.md` skill files from your user, project, or installed plugin directories before their instructions reach the context window. Clean skill files are cached by content hash; flagged skills are blocked (`/name` expansion) or denied with the reason shown to Claude (`Skill` tool); uncertain verdicts ask you. Built-in skills with no file on disk keep the regular tool-call verdict.
- **Web (`PostToolUse` on `WebFetch` & `WebSearch`):** Screens fetched web content for prompt injection and hidden instructions. Flagged content appends an untrusted-data warning context for Claude, never replaces or hides original text.

Both scopes are **on by default** with no additional configuration.

To configure or disable scanning scopes, run the bundled setup skill:

```bash
/tribunal:setup-scanning
```

### Content Screening Limitations & Cost
- **Cost:** One jev SLM call per web fetch/search result. Skills are content-addressed and cached upon clean verdict; repeated invocations cost zero additional SLM calls until file modification.
- **Scope Limits:** A small model catches overt injection, not skilled obfuscation; the per-tool-call gate remains the backstop for whatever a bad skill or page tries to *do*. Only `SKILL.md` / command files are screened: reference files a skill later loads with `Read` are not (`Read` is on the fast path).

---

## Installation

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
| `TRIBUNAL_SCAN` | Content screening scopes: `skills,web` (both), `skills`, `web`, or `off` | `skills,web` |
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

Tribunal uses Python 3 standard library only (`unittest`, `urllib`, `json`) with no external pip dependencies:

```bash
python3 -m unittest discover -s tests -v
```
