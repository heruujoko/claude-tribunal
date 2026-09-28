import contextlib
import io
import json
import os
import subprocess
import unittest
from unittest.mock import patch

from hooks import tribunal

SCRIPT = "hooks/tribunal.py"


def run_hook(stdin_text):
    env = {**os.environ, "TRIBUNAL_PROVIDER": "hosted", "JEV_API_KEY": "",
           "TRIBUNAL_CONFIG": "/nonexistent.json"}
    return subprocess.run(["python3", SCRIPT], input=stdin_text,
                          capture_output=True, text=True, env=env)


class HookContractTests(unittest.TestCase):
    def test_safe_tool_emits_allow_control_json(self):
        proc = run_hook(json.dumps(
            {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}, "cwd": "/tmp"}))
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")

    def test_bad_stdin_exits_nonblocking(self):
        proc = run_hook("not json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")

    def test_no_api_key_asks(self):
        proc = run_hook(json.dumps(
            {"tool_name": "Write", "tool_input": {}, "cwd": "/tmp"}))
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_invalid_provider_asks_explicitly(self):
        env = {**os.environ, "CCV_PROVIDER": "typo", "JEV_API_KEY": ""}
        proc = subprocess.run(["python3", SCRIPT], input=json.dumps(
            {"tool_name": "Write", "tool_input": {}, "cwd": "/tmp"}),
            capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]
                         ["permissionDecision"], "ask")

    def test_missing_cloudflare_account_asks_before_network(self):
        env = {**os.environ, "CCV_PROVIDER": "cloudflare",
               "CLOUDFLARE_ACCOUNT_ID": "", "CLOUDFLARE_API_TOKEN": "test",
               "CCV_CONFIG": "/nonexistent.json"}
        proc = subprocess.run(["python3", SCRIPT], input=json.dumps(
            {"tool_name": "Write", "tool_input": {}, "cwd": "/tmp"}),
            capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]
                         ["permissionDecision"], "ask")

    def test_invalid_numeric_setting_asks_explicitly(self):
        env = {**os.environ, "CCV_PROVIDER": "hosted", "CCV_TIMEOUT": "oops",
               "CCV_CONFIG": "/nonexistent.json"}
        proc = subprocess.run(["python3", SCRIPT], input=json.dumps(
            {"tool_name": "Write", "tool_input": {}, "cwd": "/tmp"}),
            capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]
                         ["permissionDecision"], "ask")

    def test_hosted_transport_failure_asks(self):
        env = {**os.environ, "CCV_PROVIDER": "hosted", "JEV_API_KEY": "test",
               "CCV_JEV_URL": "http://127.0.0.1:1/v1/decide",
               "CCV_TIMEOUT": "1", "CCV_CONFIG": "/nonexistent.json"}
        proc = subprocess.run(["python3", SCRIPT], input=json.dumps(
            {"tool_name": "Write", "tool_input": {}, "cwd": "/tmp"}),
            capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]
                         ["permissionDecision"], "ask")

    def test_malformed_cloudflare_envelopes_ask(self):
        cfg = tribunal.load_config(env={
            "TRIBUNAL_PROVIDER": "cloudflare", "CLOUDFLARE_ACCOUNT_ID": "acc123",
            "CLOUDFLARE_API_TOKEN": "dummy-token", "TRIBUNAL_CONFIG": "/nonexistent.json",
        })
        malformed = (None, [], "invalid", 42)
        bodies = list(malformed)
        bodies.extend({"success": True, "errors": [], "result": value}
                      for value in malformed)
        bodies.extend({"success": True, "errors": [], "result": {
            "state": "Completed", "result": value}} for value in malformed)
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        for body in bodies:
            with self.subTest(body=body):
                out, err = io.StringIO(), io.StringIO()
                with patch.object(tribunal, "load_config", return_value=cfg), \
                        patch.object(tribunal.sys, "stdin", io.StringIO(payload)), \
                        patch.object(tribunal.urllib.request, "urlopen",
                                     return_value=io.BytesIO(json.dumps(body).encode())), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    tribunal.main()  # Must return normally, not exit nonblocking.
                self.assertEqual(err.getvalue(), "")
                self.assertEqual(len(out.getvalue().splitlines()), 1)
                result = json.loads(out.getvalue())["hookSpecificOutput"]
                self.assertEqual(result["hookEventName"], "PreToolUse")
                self.assertEqual(result["permissionDecision"], "ask")
                self.assertNotIn("dummy-token", out.getvalue())

    def test_unexpected_internal_failure_exits_nonblocking(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        out, err = io.StringIO(), io.StringIO()
        with patch.object(tribunal.sys, "stdin", io.StringIO(payload)), \
                patch.object(tribunal, "load_config", side_effect=RuntimeError("internal")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as raised:
                tribunal.main()
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "tribunal: RuntimeError\n")

    def test_malformed_rules_file_asks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w") as f:
                f.write("not json")
            env = {**os.environ, "CCV_PROVIDER": "hosted", "CCV_CONFIG": path}
            proc = subprocess.run(["python3", SCRIPT], input=json.dumps(
                {"tool_name": "Write", "tool_input": {}, "cwd": "/tmp"}),
                capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]
                         ["permissionDecision"], "ask")


    def test_legacy_validator_script_wrapper(self):
        proc = subprocess.run(["python3", "hooks/validator.py"],
                              input=json.dumps({"tool_name": "Read",
                                                "tool_input": {"file_path": "/tmp/x"},
                                                "cwd": "/tmp"}),
                              capture_output=True, text=True,
                              env={**os.environ, "TRIBUNAL_PROVIDER": "hosted",
                                   "JEV_API_KEY": "", "TRIBUNAL_CONFIG": "/nonexistent.json"})
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
