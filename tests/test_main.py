import json
import os
import subprocess
import unittest

SCRIPT = "hooks/validator.py"


def run_hook(stdin_text):
    env = {**os.environ, "CCV_PROVIDER": "hosted", "JEV_API_KEY": "",
           "CCV_CONFIG": "/nonexistent.json"}
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


if __name__ == "__main__":
    unittest.main()
