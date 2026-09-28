import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from hooks.tribunal import build_request, evaluate, load_config, real_post

CFG = load_config(env={"CCV_JEV_URL": "https://jev.example/api/v1/decide",
                       "JEV_API_KEY": "jv_live_test"})


def fake_post(answer):
    return lambda body, cfg: answer


class BuildRequestTests(unittest.TestCase):
    def test_request_shape(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"},
                   "cwd": "/home/me"}
        body = build_request(payload, CFG)
        self.assertEqual(body["model"], "jev-latest")
        self.assertEqual(body["state"]["cwd"], "/home/me")
        self.assertEqual(body["state"]["tool"], "Bash")
        self.assertIn("rm -rf /", body["state"]["input"])
        q = body["questions"]["verdict"]
        self.assertEqual(q["type"], "choice")
        self.assertEqual(sorted(q["criteria"]), ["allowed", "human_ask", "rejected"])

    def test_oversized_input_never_reaches_builder(self):
        payload = {"tool_name": "Write", "tool_input": {"content": "A" * 20000}}
        self.assertEqual(evaluate(payload, CFG, lambda *_: self.fail("network"))[0],
                         "ask")

    def test_multibyte_input_budget_asks(self):
        payload = {"tool_name": "Write", "tool_input": {"content": "🔥" * 8000}}
        self.assertEqual(evaluate(payload, CFG, lambda *_: self.fail("network"))[0],
                         "ask")

    def test_cloudflare_wraps_in_input(self):
        cf_cfg = load_config(env={"CCV_PROVIDER": "cloudflare",
                                  "CLOUDFLARE_ACCOUNT_ID": "acc123",
                                  "CLOUDFLARE_API_TOKEN": "cf-token"})
        payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/t"}
        body = build_request(payload, cf_cfg)
        self.assertEqual(body["model"], "typesafe/jev")
        self.assertNotIn("state", body)  # wrapped, not top-level
        self.assertIn("state", body["input"])
        self.assertIn("questions", body["input"])


class EvaluateJevPathTests(unittest.TestCase):
    def test_allowed_maps_to_allow(self):
        payload = {"tool_name": "Write", "tool_input": {}}
        decision, reason = evaluate(
            payload, CFG, fake_post({"type": "choice", "choice": "allowed", "confidence": 0.95}))
        self.assertEqual(decision, "allow")
        self.assertIn("allowed", reason)

    def test_rejected_maps_to_deny(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
        decision, reason = evaluate(
            payload, CFG, fake_post({"type": "choice", "choice": "rejected", "confidence": 0.9}))
        self.assertEqual(decision, "deny")
        self.assertIn("rejected", reason)

    def test_unusable_answer_asks(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "make"}}
        decision, _ = evaluate(payload, CFG, fake_post({"type": "choice", "choice": "huh"}))
        self.assertEqual(decision, "ask")

    def test_wrong_response_type_asks(self):
        payload = {"tool_name": "Write", "tool_input": {}}
        decision, _ = evaluate(payload, CFG, fake_post({
            "type": "score", "choice": "allowed", "confidence": 1.0}))
        self.assertEqual(decision, "ask")


class RealPostTests(unittest.TestCase):
    def _response(self, answer):
        return io.BytesIO(json.dumps(
            {"model": "jev-1.13.0", "answers": {"verdict": answer},
             "usage": {"input_tokens": 62}}).encode())

    def test_posts_and_extracts_verdict(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
            captured["body"] = json.loads(req.data.decode())
            captured["timeout"] = timeout
            return self._response({"type": "choice", "choice": "allowed", "confidence": 0.99})

        with patch("hooks.tribunal.urllib.request.urlopen", fake_urlopen):
            answer = real_post({"model": "jev-latest"}, CFG)

        self.assertEqual(answer["choice"], "allowed")
        self.assertEqual(captured["url"], "https://jev.example/api/v1/decide")
        self.assertEqual(captured["auth"], "Bearer jv_live_test")
        self.assertEqual(captured["body"]["model"], "jev-latest")
        self.assertEqual(captured["timeout"], 10)

    def test_missing_key_never_hits_network(self):
        payload = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x"}}
        for env in ({"CCV_JEV_URL": "https://jev.example/api/v1/decide"},
                    {"CCV_PROVIDER": "cloudflare", "CLOUDFLARE_ACCOUNT_ID": "acc123"}):
            cfg = load_config(env=env)
            with self.subTest(env=env), patch("hooks.tribunal.urllib.request.urlopen",
                                             side_effect=AssertionError("network called")):
                decision, _ = evaluate(payload, cfg, real_post)
            self.assertEqual(decision, "ask")

    def test_http_error_propagates(self):
        with patch("hooks.tribunal.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("down")):
            with self.assertRaises(urllib.error.URLError):
                real_post({"model": "jev-latest"}, CFG)

    def test_missing_answers_key_raises(self):
        with patch("hooks.tribunal.urllib.request.urlopen",
                   return_value=io.BytesIO(b'{"model": "jev-1.13.0"}')):
            with self.assertRaises(KeyError):
                real_post({"model": "jev-latest"}, CFG)

    def test_cloudflare_envelope_unwrapped(self):
        # exact live-captured shape (abridged): answers nested at result.result
        cf_cfg = load_config(env={"CCV_PROVIDER": "cloudflare",
                                  "CLOUDFLARE_ACCOUNT_ID": "acc123",
                                  "CLOUDFLARE_API_TOKEN": "cf-token"})
        cf_body = json.dumps({"result": {"state": "Completed", "result": {
            "answers": {"verdict": {"type": "choice", "choice": "rejected", "confidence": 0.99}}}},
            "success": True, "errors": []}).encode()
        with patch("hooks.tribunal.urllib.request.urlopen",
                   return_value=io.BytesIO(cf_body)):
            answer = real_post({"model": "typesafe/jev"}, cf_cfg)
        self.assertEqual(answer["choice"], "rejected")

    def test_cloudflare_failed_envelope_never_approves(self):
        cf_cfg = load_config(env={"CCV_PROVIDER": "cloudflare",
                                  "CLOUDFLARE_ACCOUNT_ID": "acc123",
                                  "CLOUDFLARE_API_TOKEN": "cf-token"})
        for status in ({"success": False, "errors": []},
                       {"success": True, "errors": ["failure"]},
                       {"success": True, "errors": [], "state": "Pending"}):
            body = json.dumps({"result": {"state": status.get("state", "Completed"),
                "result": {"answers": {"verdict": {"type": "choice", "choice": "allowed",
                    "confidence": 1.0}}}}, "success": status["success"],
                "errors": status["errors"]}).encode()
            with self.subTest(status=status), patch(
                    "hooks.tribunal.urllib.request.urlopen",
                    return_value=io.BytesIO(body)):
                with self.assertRaises(ValueError):
                    real_post({}, cf_cfg)


if __name__ == "__main__":
    unittest.main()
