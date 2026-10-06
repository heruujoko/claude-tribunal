import contextlib
import io
import json
import unittest
from unittest.mock import patch

from hooks import tribunal


class NativeDecisionTests(unittest.TestCase):
    def run_native(self, answer=None, error=None, payload=None, env=None):
        payload = payload or {"tool_name": "Bash", "tool_input": {"command": "make"}}
        cfg = tribunal.load_config(env={"JEV_API_KEY": "test", **(env or {})})
        out = io.StringIO()
        with patch.object(tribunal.sys, "argv", ["tribunal.py", "--native"]), \
                patch.object(tribunal.sys, "stdin", io.StringIO(json.dumps(payload))), \
                patch.object(tribunal, "load_config", return_value=cfg), \
                patch.object(tribunal, "real_post", return_value=answer, side_effect=error), \
                contextlib.redirect_stdout(out):
            tribunal.main()
        return json.loads(out.getvalue())

    def test_only_confident_human_ask_is_eligible(self):
        for choice in ("allowed", "rejected", "human_ask", "unknown"):
            for confidence in (None, False, -1, 0.2, 0.9, 2, float('nan'), float('inf')):
                with self.subTest(choice=choice, confidence=confidence):
                    result = self.run_native({"type": "choice", "choice": choice,
                                              "confidence": confidence})
                    self.assertEqual(result["respect_saved_permission"],
                                     choice == "human_ask" and confidence == 0.9)

    def test_failures_and_input_cannot_claim_consent(self):
        cases = (
            {"answer": {"type": "score", "choice": "human_ask", "confidence": 1}},
            {"error": OSError("secret")},
            {"env": {"JEV_API_KEY": ""}},
            {"payload": {"tool_name": "Bash", "tool_input": {"command": "x" * 8193},
                         "respect_saved_permission": True}},
        )
        for case in cases:
            with self.subTest(case=case):
                result = self.run_native(**case)
                self.assertEqual(result["decision"], "ask")
                self.assertFalse(result["respect_saved_permission"])
                self.assertNotIn("secret", result["reason"])

    def test_fast_path_is_not_a_saved_permission(self):
        result = self.run_native(payload={"tool_name": "Read", "tool_input": {}})
        self.assertEqual(result["decision"], "allow")
        self.assertFalse(result["respect_saved_permission"])


if __name__ == "__main__":
    unittest.main()
