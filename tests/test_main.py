import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from hooks import tribunal, profiles
from tests.helpers import HomeTestCase, clean_env

ROOT = Path(__file__).resolve().parents[1]


class HookContractTests(HomeTestCase):
    def run_hook(self, payload, extra=None, native=False, script="tribunal.py"):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(
            [sys.executable, "-I", str(ROOT / "hooks" / script),
             *(["--native"] if native else [])],
            input=text, capture_output=True, text=True, timeout=10,
            env=clean_env(self.home, extra))

    def test_safe_tool_emits_allow_control_json(self):
        proc = self.run_hook({"tool_name": "Read", "tool_input": {}})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(out["hookEventName"], "PreToolUse")

    def test_bad_stdin_exits_nonblocking(self):
        proc = self.run_hook("not json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")

    def test_no_api_key_asks(self):
        proc = self.run_hook({"tool_name": "Write", "tool_input": {}})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]
                         ["permissionDecision"], "ask")

    def test_invalid_provider_asks_explicitly(self):
        self.assert_asks({"CCV_PROVIDER": "typo"})

    def test_missing_cloudflare_account_asks_before_network(self):
        self.assert_asks({"CCV_PROVIDER": "cloudflare",
                         "CLOUDFLARE_ACCOUNT_ID": "", "CLOUDFLARE_API_TOKEN": "test"})

    def test_invalid_numeric_setting_asks_explicitly(self):
        self.assert_asks({"CCV_TIMEOUT": "oops"})

    def test_hosted_transport_failure_asks(self):
        self.assert_asks({"JEV_API_KEY": "test", "CCV_JEV_URL": "http://127.0.0.1:1/decide",
                         "CCV_TIMEOUT": "1"})

    def assert_asks(self, extra):
        proc = self.run_hook({"tool_name": "Write", "tool_input": {}}, extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]
                         ["permissionDecision"], "ask")

    def test_corrupt_profile_asks_even_on_fast_path(self):
        os.makedirs(profiles.store_dir(self.home))
        payloads = ({"tool_name": "Read", "tool_input": {}},
                    {"tool_name": "Bash", "tool_input": {"command": "git status"}})
        for raw in (b"not json", b"{}", b'{"active":"missing","custom":{}}',
                    b"\xff", b"x" * (profiles.MAX_FILE + 1)):
            with open(profiles.store_path(self.home), "wb") as f:
                f.write(raw)
            for payload in payloads:
                for native in (False, True):
                    with self.subTest(raw=raw[:30], tool=payload["tool_name"], native=native):
                        proc = self.run_hook(payload, native=native)
                        self.assertEqual(proc.returncode, 0, proc.stderr)
                        result = json.loads(proc.stdout)
                        if native:
                            self.assertEqual(result["decision"], "ask")
                            self.assertFalse(result["respect_saved_permission"])
                        else:
                            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "ask")

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
                        patch.object(tribunal.sys, "argv", ["tribunal.py"]), \
                        patch.object(tribunal.sys, "stdin", io.StringIO(payload)), \
                        patch.object(tribunal.urllib.request, "urlopen",
                                     return_value=io.BytesIO(json.dumps(body).encode())), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    tribunal.main()
                self.assertEqual(err.getvalue(), "")
                self.assertEqual(len(out.getvalue().splitlines()), 1)
                result = json.loads(out.getvalue())["hookSpecificOutput"]
                self.assertEqual(result["hookEventName"], "PreToolUse")
                self.assertEqual(result["permissionDecision"], "ask")
                self.assertNotIn("dummy-token", out.getvalue())

    def test_unexpected_internal_failure_exits_nonblocking(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(tribunal.sys, "stdin", io.StringIO('{"tool_name":"Bash"}')), \
                patch.object(tribunal, "load_config", side_effect=RuntimeError("internal")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as raised:
                tribunal.main()
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "tribunal: RuntimeError\n")

    def test_malformed_rules_file_asks(self):
        path = os.path.join(self.home, "config.json")
        with open(path, "w") as f:
            f.write("not json")
        self.assert_asks({"TRIBUNAL_CONFIG": path})

    def test_legacy_validator_script_wrapper(self):
        proc = self.run_hook({"tool_name": "Read", "tool_input": {}}, script="validator.py")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
