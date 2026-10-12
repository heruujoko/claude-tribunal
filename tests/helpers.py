"""Managed homes and credential-free environments for evaluator tests."""
import os
import tempfile
import unittest
from unittest.mock import patch


def clean_env(home, extra=None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("TRIBUNAL_", "CCV_", "CLOUDFLARE_"))
           and k not in ("JEV_API_KEY", "CLAUDE_CONFIG_DIR")}
    env.update(HOME=home, TRIBUNAL_CONFIG=os.path.join(home, "no-config.json"))
    env.update(extra or {})
    return env


class HomeTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="tribunal-test-")
        self.addCleanup(directory.cleanup)
        self.home = directory.name
        env = patch.dict(os.environ, clean_env(self.home), clear=True)
        env.start()
        self.addCleanup(env.stop)
