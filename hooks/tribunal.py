#!/usr/bin/env python3
"""PreToolUse hook: ask a jev decide endpoint to verdict each tool call.

Outputs Claude Code control JSON on stdout. Any internal failure exits
non-blocking (exit 1) so Claude Code's native permission flow stays in charge.
"""
import json
import math
import os
import sys
import urllib.request

CHOICE_MAP = {"allowed": "allow", "rejected": "deny", "human_ask": "ask"}
MAX_INPUT_BYTES = 8192
SCAN_SCOPES = frozenset({"skills", "web"})
DEFAULT_ENDPOINT = "https://jevtypesafeai.com/api/v1/decide"
DEFAULT_JEV_URL = DEFAULT_ENDPOINT  # backwards compatibility alias
DEFAULT_SAFE_TOOLS = ["Read", "Glob", "Grep", "TodoWrite",
                      "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
DEFAULT_SAFE_COMMANDS = ["git status", "pwd"]
VERDICT_INSTRUCTIONS = (
    "Should an AI agent be allowed to run this tool call on the user's machine? "
    "Pick human_ask when uncertain or when a human should decide."
)
VERDICT_CRITERIA = {
    "allowed": "clearly safe and reversible for this machine",
    "rejected": "clearly unsafe, destructive, or against the user's interest",
    "human_ask": "uncertain, sensitive, or needing human judgment",
}


def _plugin_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def scan_scopes(env):
    """TRIBUNAL_SCAN -> enabled scopes. Unset/empty/invalid -> both (fail tight); 'off' -> none."""
    raw = env.get("TRIBUNAL_SCAN", "").strip().lower()
    if raw == "off":
        return set()
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    return parts if parts and parts <= SCAN_SCOPES else set(SCAN_SCOPES)


def chunks(text, limit=MAX_INPUT_BYTES):
    """Split into <= limit UTF-8 byte pieces on character boundaries; never drops text."""
    data, out = text.encode("utf-8"), []
    while data:
        cut = min(limit, len(data))
        while cut < len(data) and data[cut] & 0xC0 == 0x80:  # don't split a character
            cut -= 1
        out.append(data[:cut].decode("utf-8"))
        data = data[cut:]
    return out


def _get_env_var(env, suffix, default=None):
    """Retrieve TRIBUNAL_<suffix> with fallback to CCV_<suffix> for backwards compatibility."""
    if f"TRIBUNAL_{suffix}" in env:
        return env[f"TRIBUNAL_{suffix}"]
    if f"CCV_{suffix}" in env:
        return env[f"CCV_{suffix}"]
    return default


def load_config(env=None):
    env = os.environ if env is None else env
    provider = _get_env_var(env, "PROVIDER", "hosted")
    if provider not in ("hosted", "cloudflare"):
        raise ValueError("invalid TRIBUNAL_PROVIDER")
    try:
        timeout = int(_get_env_var(env, "TIMEOUT", "10"))
        confidence = float(_get_env_var(env, "MIN_CONFIDENCE", "0.5"))
    except ValueError as exc:
        raise ValueError("invalid numeric setting") from exc
    if timeout <= 0 or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("invalid timeout or confidence threshold")
    cfg = {
        "provider": provider,
        "model": _get_env_var(env, "MODEL",
                              "typesafe/jev" if provider == "cloudflare" else "jev-latest"),
        "timeout": timeout,
        "min_confidence": confidence,
        "safe_tools": DEFAULT_SAFE_TOOLS,
        "safe_commands": DEFAULT_SAFE_COMMANDS,
    }
    if provider == "cloudflare":
        account = env.get("CLOUDFLARE_ACCOUNT_ID", "")
        if not account or not account.isalnum():
            raise ValueError("invalid CLOUDFLARE_ACCOUNT_ID")
        endpoint = (f"https://api.cloudflare.com/client/v4"
                    f"/accounts/{account}/ai/run")
        cfg["endpoint"] = endpoint
        cfg["jev_url"] = endpoint  # backwards compatibility alias
        cfg["api_key"] = env.get("CLOUDFLARE_API_TOKEN", "")
    else:
        endpoint = (env.get("TRIBUNAL_ENDPOINT")
                    or env.get("TRIBUNAL_API_URL")
                    or _get_env_var(env, "JEV_URL")
                    or DEFAULT_ENDPOINT)
        cfg["endpoint"] = endpoint
        cfg["jev_url"] = endpoint  # backwards compatibility alias
        cfg["api_key"] = (env.get("TRIBUNAL_API_KEY")
                          or env.get("JEV_API_KEY", ""))
    path = _get_env_var(env, "CONFIG") or os.path.join(_plugin_root(), "config.json")
    if os.path.exists(path):
        with open(path) as f:
            rules = json.load(f)
        if not isinstance(rules, dict) or set(rules) - {"safe_tools", "safe_commands"}:
            raise ValueError("rules file may only replace safe_tools and safe_commands")
        for key, values in rules.items():
            defaults = DEFAULT_SAFE_TOOLS if key == "safe_tools" else DEFAULT_SAFE_COMMANDS
            if (not isinstance(values, list) or not all(isinstance(v, str) for v in values)
                    or any(v not in defaults for v in values)):
                raise ValueError(f"invalid {key} fast-path rules")
        cfg.update(rules)
    return cfg


def map_answer(answer, min_confidence):
    """jev answers.verdict -> permissionDecision, or None if unusable.

    Missing, non-numeric, non-finite, or out-of-range confidence cannot approve
    a tool call; a confidence below the threshold asks the human.
    """
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        return None
    decision = CHOICE_MAP.get(answer.get("choice"))
    if decision is None:
        return None
    confidence = answer.get("confidence")
    if (type(confidence) not in (int, float) or not math.isfinite(confidence)
            or not 0 <= confidence <= 1 or confidence < min_confidence):
        return "ask"
    return decision


def build_request(payload, cfg):
    tool = payload.get("tool_name", "")
    raw = json.dumps(payload.get("tool_input", {}), default=str, ensure_ascii=False)
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("tool input exceeds tribunal budget")
    # evaluate() returns ask before calling this builder when the input is too large.
    core = {
        "state": {"cwd": payload.get("cwd", ""), "tool": tool, "input": raw},
        "questions": {
            "verdict": {
                "type": "choice",
                "instructions": VERDICT_INSTRUCTIONS,
                "criteria": VERDICT_CRITERIA,
            }
        },
    }
    # Cloudflare /ai/run wraps state+questions inside "input" (live-proven envelope)
    if cfg["provider"] == "cloudflare":
        return {"model": cfg["model"], "input": core}
    return {"model": cfg["model"], **core}


def extract_answer(data, provider):
    """Only completed, error-free Cloudflare responses can yield a verdict.

    Cloudflare's nested envelope was captured live (docs/research/
    2026-09-22-prototype-evidence.md).
    """
    if provider == "cloudflare":
        if not isinstance(data, dict) or not isinstance(data.get("result"), dict):
            raise ValueError("invalid Cloudflare envelope")
        if (data.get("success") is not True or data.get("errors") != []
                or data["result"].get("state") != "Completed"):
            raise ValueError("Cloudflare did not complete successfully")
        data = data["result"]["result"]
    return data["answers"]["verdict"]


def real_post(body, cfg):
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    target_url = cfg.get("endpoint") or cfg.get("jev_url")
    req = urllib.request.Request(target_url, data=json.dumps(body).encode(),
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
        data = json.load(resp)
    return extract_answer(data, cfg["provider"])


def evaluate(payload, cfg, post):
    """Tool-call payload -> (permissionDecision, reason). post(body, cfg) -> answers.verdict."""
    tool = payload.get("tool_name", "")
    if tool in cfg["safe_tools"]:
        return "allow", "fast path: safe tool"
    if tool == "Bash":
        cmd = (payload.get("tool_input") or {}).get("command", "")
        if cmd in cfg["safe_commands"]:
            return "allow", "fast path: safe command"
    raw = json.dumps(payload.get("tool_input", {}), default=str, ensure_ascii=False)
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        return "ask", "tool input exceeds tribunal budget"
    if not cfg["api_key"]:
        return "ask", "provider API key not set"
    answer = post(build_request(payload, cfg), cfg)
    decision = map_answer(answer, cfg["min_confidence"])
    if decision is None:
        return "ask", "unusable jev answer"
    choice = answer.get("choice")
    confidence = answer.get("confidence")
    return decision, f"jev: {choice} (confidence {confidence})"


def emit(decision, reason=""):
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}, sys.stdout)
    sys.stdout.write("\n")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(f"tribunal: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)

    try:
        decision, reason = evaluate(payload, load_config(), real_post)
        emit(decision, reason)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Known config/provider/transport errors should force a human prompt.
        emit("ask", f"tribunal unavailable: {type(exc).__name__}")
    except Exception as exc:  # unexpected failure: native permissions remain in charge
        print(f"tribunal: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
