#!/usr/bin/env python3
"""PreToolUse hook: ask a jev decide endpoint to verdict each tool call.

Outputs Claude Code control JSON on stdout. Any internal failure exits
non-blocking (exit 1) so Claude Code's native permission flow stays in charge.
"""
import json
import math
import sys

CHOICE_MAP = {"allowed": "allow", "rejected": "deny", "human_ask": "ask"}
MAX_INPUT_BYTES = 8192


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
