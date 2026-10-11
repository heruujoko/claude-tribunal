"""Tests for hooks/profiles.py: storage, CLI, validation, concurrency."""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

from hooks import profiles


SCRIPT = "hooks/profiles.py"


def run_cli(argv, stdin_text="", home=None):
    env = {k: v for k, v in os.environ.items() if k not in ("HOME", "CLAUDE_CONFIG_DIR")}
    env["HOME"] = home if home is not None else tempfile.mkdtemp()
    proc = subprocess.run(
        [sys.executable, "-I", SCRIPT, *argv],
        input=stdin_text, capture_output=True, text=True, env=env, timeout=10)
    return proc, env["HOME"]


class BuiltinTests(unittest.TestCase):
    def test_three_builtins_immutable(self):
        self.assertEqual(set(profiles.BUILTIN), {"developer", "office-design", "browsing"})

    def test_security_text_includes_all_concerns(self):
        for term in ("credential", "destructive", "injection", "supply-chain",
                     "evidence", "not proof", "temporary path"):
            self.assertIn(term.lower(), profiles.SECURITY.lower())

    def test_default_is_developer(self):
        self.assertEqual(profiles.DEFAULT, "developer")


class LoadTests(unittest.TestCase):
    def test_missing_file_defaults_to_developer(self):
        home = tempfile.mkdtemp()
        p = profiles.load(home)
        self.assertEqual(p["name"], "developer")
        self.assertEqual(p["guidance"], profiles.BUILTIN["developer"])
        self.assertIsNone(p["custom"])
        self.assertFalse(os.path.exists(profiles.store_path(home)))

    def test_switch_to_office_design(self):
        home = tempfile.mkdtemp()
        profiles.switch("office-design", home)
        p = profiles.load(home)
        self.assertEqual(p["name"], "office-design")
        self.assertEqual(p["guidance"], profiles.BUILTIN["office-design"])

    def test_switch_to_browsing(self):
        home = tempfile.mkdtemp()
        profiles.switch("browsing", home)
        p = profiles.load(home)
        self.assertEqual(p["name"], "browsing")

    def test_persistence_across_reads(self):
        home = tempfile.mkdtemp()
        profiles.switch("browsing", home)
        p = profiles.load(home)
        self.assertEqual(p["name"], "browsing")

    def test_unknown_active_profile_raises(self):
        home = tempfile.mkdtemp()
        os.makedirs(profiles.store_dir(home), exist_ok=True)
        with open(profiles.store_path(home), "w") as f:
            json.dump({"active": "nonexistent", "custom": {}}, f)
        with self.assertRaises(ValueError):
            profiles.load(home)


class CustomProfileTests(unittest.TestCase):
    def test_create_custom_profile(self):
        home = tempfile.mkdtemp()
        spec = {
            "name": "data-analysis",
            "purpose": "Analyze CSV files and generate reports",
            "routine_tasks": ["Read CSV files", "Run pandas scripts", "Write reports"],
            "ask_before": ["Delete files", "Send emails"]
        }
        profiles.create(spec, home)
        store = profiles.read_store(home)
        self.assertIn("data-analysis", store["custom"])
        self.assertEqual(store["active"], "developer")  # not activated

    def test_create_does_not_activate(self):
        home = tempfile.mkdtemp()
        spec = {
            "name": "my-profile",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"]
        }
        profiles.create(spec, home)
        self.assertEqual(profiles.load(home)["name"], "developer")

    def test_switch_to_custom_after_create(self):
        home = tempfile.mkdtemp()
        spec = {
            "name": "my-profile",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"]
        }
        profiles.create(spec, home)
        profiles.switch("my-profile", home)
        p = profiles.load(home)
        self.assertEqual(p["name"], "my-profile")
        self.assertEqual(p["guidance"], profiles.CUSTOM_NOTE)
        self.assertEqual(p["custom"]["purpose"], "Test")

    def test_custom_name_collision_with_builtin(self):
        home = tempfile.mkdtemp()
        spec = {
            "name": "developer",
            "purpose": "Override",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"]
        }
        with self.assertRaises(ValueError):
            profiles.create(spec, home)

    def test_custom_name_collision_with_existing(self):
        home = tempfile.mkdtemp()
        spec = {
            "name": "my-profile",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"]
        }
        profiles.create(spec, home)
        with self.assertRaises(ValueError):
            profiles.create(spec, home)

    def test_custom_profile_loads_with_custom_guidance(self):
        home = tempfile.mkdtemp()
        spec = {
            "name": "my-profile",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"]
        }
        profiles.create(spec, home)
        profiles.switch("my-profile", home)
        p = profiles.load(home)
        self.assertIn("custom_profile", p["guidance"])
        self.assertIn("lower-priority", p["guidance"])


class ValidationTests(unittest.TestCase):
    def test_invalid_name_rejected(self):
        for name in ("UPPER", "with space", "with_underscore", "-starts-dash",
                     "", "a" * 40, "12345678901234567890123456789012"):
            with self.assertRaises(ValueError):
                profiles.check_name(name)

    def test_valid_names_accepted(self):
        for name in ("my-profile", "a", "data-analysis-2024", "test123"):
            profiles.check_name(name)

    def test_invalid_field_types_rejected(self):
        home = tempfile.mkdtemp()
        cases = [
            {"name": "p", "purpose": 123, "routine_tasks": [], "ask_before": []},
            {"name": "p", "purpose": "", "routine_tasks": [], "ask_before": []},
            {"name": "p", "purpose": "x" * 400, "routine_tasks": [], "ask_before": []},
            {"name": "p", "purpose": "ok", "routine_tasks": "not-list", "ask_before": []},
            {"name": "p", "purpose": "ok", "routine_tasks": [], "ask_before": []},
            {"name": "p", "purpose": "ok", "routine_tasks": ["a"] * 15, "ask_before": []},
            {"name": "p", "purpose": "ok", "routine_tasks": [""], "ask_before": []},
            {"name": "p", "purpose": "ok", "routine_tasks": ["a" * 250], "ask_before": []},
        ]
        for spec in cases:
            with self.assertRaises(ValueError):
                profiles.create(spec, home)

    def test_extra_fields_rejected(self):
        home = tempfile.mkdtemp()
        spec = {
            "name": "p",
            "purpose": "ok",
            "routine_tasks": ["task"],
            "ask_before": ["action"],
            "extra": "field"
        }
        with self.assertRaises(ValueError):
            profiles.create(spec, home)

    def test_missing_fields_rejected(self):
        home = tempfile.mkdtemp()
        spec = {"name": "p", "purpose": "ok"}
        with self.assertRaises(ValueError):
            profiles.create(spec, home)


class StorageTests(unittest.TestCase):
    def test_symlink_refused(self):
        home = tempfile.mkdtemp()
        profiles.switch("browsing", home)
        real = profiles.store_path(home)
        link = real + ".link"
        os.symlink(real, link)
        os.unlink(real)
        os.symlink(link, real)
        with self.assertRaises(ValueError):
            profiles.switch("developer", home)

    def test_oversized_file_rejected(self):
        home = tempfile.mkdtemp()
        os.makedirs(profiles.store_dir(home), exist_ok=True)
        with open(profiles.store_path(home), "w") as f:
            f.write('{"active": "developer", "custom": {}, "extra": "' + "x" * 70000 + '"}')
        with self.assertRaises(ValueError):
            profiles.load(home)

    def test_malformed_json_asks(self):
        home = tempfile.mkdtemp()
        os.makedirs(profiles.store_dir(home), exist_ok=True)
        with open(profiles.store_path(home), "w") as f:
            f.write("not json")
        with self.assertRaises(Exception):
            profiles.load(home)

    def test_atomic_write_no_data_loss(self):
        home = tempfile.mkdtemp()
        profiles.switch("browsing", home)
        spec = {
            "name": "test",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"]
        }
        profiles.create(spec, home)
        store = profiles.read_store(home)
        self.assertEqual(store["active"], "browsing")
        self.assertIn("test", store["custom"])

    def test_concurrent_creation_serialized(self):
        home = tempfile.mkdtemp()
        errors = []
        def create_one(i):
            try:
                spec = {
                    "name": f"profile-{i}",
                    "purpose": f"Purpose {i}",
                    "routine_tasks": [f"Task {i}"],
                    "ask_before": [f"Action {i}"]
                }
                profiles.create(spec, home)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=create_one, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(errors), 0)
        store = profiles.read_store(home)
        self.assertEqual(len(store["custom"]), 5)


class CLITests(unittest.TestCase):
    def test_list_shows_builtins(self):
        proc, home = run_cli(["list"])
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["active"], "developer")
        self.assertEqual(set(out["builtin"]), {"developer", "office-design", "browsing"})
        self.assertEqual(out["custom"], {})

    def test_show_active(self):
        proc, home = run_cli(["show"])
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["active"], "developer")

    def test_switch_builtin(self):
        home = tempfile.mkdtemp()
        proc, _ = run_cli(["switch", "browsing"], home=home)
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["active"], "browsing")
        proc2, _ = run_cli(["show"], home=home)
        self.assertEqual(json.loads(proc2.stdout)["active"], "browsing")

    def test_switch_unknown_fails(self):
        proc, _ = run_cli(["switch", "nonexistent"])
        self.assertNotEqual(proc.returncode, 0)

    def test_create_from_stdin(self):
        spec = {
            "name": "cli-profile",
            "purpose": "CLI test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"]
        }
        proc, home = run_cli(["create"], json.dumps(spec))
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["created"], "cli-profile")
        self.assertEqual(out["active"], "developer")

    def test_create_invalid_stdin_fails(self):
        proc, _ = run_cli(["create"], json.dumps({"name": "bad"}))
        self.assertNotEqual(proc.returncode, 0)

    def test_no_args_shows_usage(self):
        proc, _ = run_cli([])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("usage", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
