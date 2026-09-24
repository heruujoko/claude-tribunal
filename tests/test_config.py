import json
import os
import tempfile
import unittest

from hooks.validator import DEFAULT_SAFE_COMMANDS, DEFAULT_SAFE_TOOLS, load_config


def write_cfg(rules):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(rules, f)
    return path


class LoadConfigTests(unittest.TestCase):
    def test_defaults(self):
        cfg = load_config(env={})
        self.assertEqual(cfg["jev_url"], "https://jevtypesafeai.com/api/v1/decide")
        self.assertEqual(cfg["model"], "jev-latest")
        self.assertEqual(cfg["timeout"], 10)
        self.assertEqual(cfg["min_confidence"], 0.5)
        self.assertEqual(cfg["safe_tools"], DEFAULT_SAFE_TOOLS)
        self.assertEqual(cfg["safe_commands"], DEFAULT_SAFE_COMMANDS)

    def test_env_overrides(self):
        cfg = load_config(env={
            "CCV_JEV_URL": "https://console.typesafe.ai/v1/systemone",
            "JEV_API_KEY": "jv_live_x",
            "CCV_MODEL": "jev-1.13.0",
            "CCV_TIMEOUT": "5",
            "CCV_MIN_CONFIDENCE": "0.7",
        })
        self.assertEqual(cfg["jev_url"], "https://console.typesafe.ai/v1/systemone")
        self.assertEqual(cfg["api_key"], "jv_live_x")
        self.assertEqual(cfg["model"], "jev-1.13.0")
        self.assertEqual(cfg["timeout"], 5)
        self.assertEqual(cfg["min_confidence"], 0.7)

    def test_cloudflare_provider(self):
        cfg = load_config(env={"CCV_PROVIDER": "cloudflare",
                               "CLOUDFLARE_ACCOUNT_ID": "acc123",
                               "CLOUDFLARE_API_TOKEN": "cf-token"})
        self.assertEqual(cfg["provider"], "cloudflare")
        self.assertEqual(cfg["jev_url"],
                         "https://api.cloudflare.com/client/v4/accounts/acc123/ai/run")
        self.assertEqual(cfg["api_key"], "cf-token")
        self.assertEqual(cfg["model"], "typesafe/jev")

    def test_invalid_provider_and_missing_account(self):
        for env in ({"CCV_PROVIDER": "typo"}, {"CCV_PROVIDER": "cloudflare"}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                load_config(env=env)

    def test_invalid_numbers(self):
        for key, value in (("CCV_TIMEOUT", "0"), ("CCV_TIMEOUT", "oops"),
                           ("CCV_MIN_CONFIDENCE", "nan"),
                           ("CCV_MIN_CONFIDENCE", "1.5")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                load_config(env={key: value})

    def test_config_file_replaces_rules(self):
        path = write_cfg({"safe_tools": ["Read"], "safe_commands": ["pwd"]})
        try:
            cfg = load_config(env={"CCV_CONFIG": path})
            self.assertEqual(cfg["safe_tools"], ["Read"])
            self.assertEqual(cfg["safe_commands"], ["pwd"])
        finally:
            os.unlink(path)

    def test_rules_file_cannot_override_provider_or_credentials(self):
        path = write_cfg({"api_key": "from-file"})
        try:
            with self.assertRaises(ValueError):
                load_config(env={"CCV_CONFIG": path})
        finally:
            os.unlink(path)

    def test_invalid_rule_types(self):
        for rules in ({"safe_tools": "Read"}, {"safe_commands": [23]},
                      {"safe_tools": ["Bash"]},
                      {"safe_commands": ["git status; rm -rf /"]}):
            path = write_cfg(rules)
            try:
                with self.subTest(rules=rules), self.assertRaises(ValueError):
                    load_config(env={"CCV_CONFIG": path})
            finally:
                os.unlink(path)

    def test_missing_config_file_ignored(self):
        cfg = load_config(env={"CCV_CONFIG": "/nonexistent.json"})
        self.assertEqual(cfg["safe_tools"], DEFAULT_SAFE_TOOLS)


if __name__ == "__main__":
    unittest.main()
