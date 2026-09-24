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
DEFAULT_JEV_URL = "https://jevtypesafeai.com/api/v1/decide"
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


def load_config(env=None):
    env = os.environ if env is None else env
    provider = env.get("CCV_PROVIDER", "hosted")
    if provider not in ("hosted", "cloudflare"):
        raise ValueError("invalid CCV_PROVIDER")
    try:
        timeout = int(env.get("CCV_TIMEOUT", "10"))
        confidence = float(env.get("CCV_MIN_CONFIDENCE", "0.5"))
    except ValueError as exc:
        raise ValueError("invalid numeric setting") from exc
    if timeout <= 0 or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("invalid timeout or confidence threshold")
    cfg = {
        "provider": provider,
        "model": env.get("CCV_MODEL",
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
        cfg["jev_url"] = (f"https://api.cloudflare.com/client/v4"
                          f"/accounts/{account}/ai/run")
        cfg["api_key"] = env.get("CLOUDFLARE_API_TOKEN", "")
    else:
        cfg["jev_url"] = env.get("CCV_JEV_URL", DEFAULT_JEV_URL)
        cfg["api_key"] = env.get("JEV_API_KEY", "")
    path = env.get("CCV_CONFIG") or os.path.join(_plugin_root(), "config.json")
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
        raise ValueError("tool input exceeds validator budget")
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
        if (data.get("success") is not True or data.get("errors") != []
                or data.get("result", {}).get("state") != "Completed"):
            raise ValueError("Cloudflare did not complete successfully")
        data = data["result"]["result"]
    return data["answers"]["verdict"]


def real_post(body, cfg):
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    req = urllib.request.Request(cfg["jev_url"], data=json.dumps(body).encode(),
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
        return "ask", "tool input exceeds validator budget"
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
        print(f"validator: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)

    try:
        decision, reason = evaluate(payload, load_config(), real_post)
        emit(decision, reason)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Known config/provider/transport errors should force a human prompt.
        emit("ask", f"validator unavailable: {type(exc).__name__}")
    except Exception as exc:  # unexpected failure: native permissions remain in charge
        print(f"validator: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
