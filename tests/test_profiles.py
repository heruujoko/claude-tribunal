"""Tests for hooks/profiles.py: storage, CLI, validation, concurrency."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from hooks import profiles
from tests.helpers import HomeTestCase, clean_env
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = str(ROOT / "hooks/profiles.py")


class ManagedHomeTestCase(HomeTestCase):
    def run_cli(self, argv, stdin_text="", home=None):
        target_home = self.home if home is None else home
        env = clean_env(target_home)
        proc = subprocess.run(
            [sys.executable, "-I", SCRIPT, *argv],
            input=stdin_text, capture_output=True, text=True, env=env, timeout=10)
        return proc, target_home


class BuiltinTests(unittest.TestCase):
    def test_three_builtins_immutable(self):
        self.assertEqual(set(profiles.BUILTIN), {"developer", "office-design", "browsing"})

    def test_security_text_includes_all_concerns(self):
        for term in ("credential", "destructive", "injection", "supply-chain",
                     "evidence", "not proof", "temporary path", "branch names are not proof"):
            self.assertIn(term.lower(), profiles.SECURITY.lower())

    def test_default_is_developer(self):
        self.assertEqual(profiles.DEFAULT, "developer")


class LoadTests(ManagedHomeTestCase):
    def test_missing_file_defaults_to_developer(self):
        p = profiles.load(self.home)
        self.assertEqual(p["name"], "developer")
        self.assertEqual(p["guidance"], profiles.BUILTIN["developer"])
        self.assertIsNone(p["custom"])
        self.assertFalse(os.path.exists(profiles.store_path(self.home)))

    def test_switch_to_office_design(self):
        profiles.switch("office-design", self.home)
        p = profiles.load(self.home)
        self.assertEqual(p["name"], "office-design")
        self.assertEqual(p["guidance"], profiles.BUILTIN["office-design"])

    def test_switch_to_browsing(self):
        profiles.switch("browsing", self.home)
        p = profiles.load(self.home)
        self.assertEqual(p["name"], "browsing")

    def test_persistence_across_reads(self):
        profiles.switch("browsing", self.home)
        p = profiles.load(self.home)
        self.assertEqual(p["name"], "browsing")

    def test_unknown_active_profile_raises(self):
        os.makedirs(profiles.store_dir(self.home), exist_ok=True)
        with open(profiles.store_path(self.home), "w") as f:
            json.dump({"active": "nonexistent", "custom": {}}, f)
        with self.assertRaises(ValueError):
            profiles.load(self.home)


class CustomProfileTests(ManagedHomeTestCase):
    def test_create_custom_profile(self):
        spec = {
            "name": "data-analysis",
            "purpose": "Analyze CSV files and generate reports",
            "routine_tasks": ["Read CSV files", "Run pandas scripts", "Write reports"],
            "ask_before": ["Delete files", "Send emails"],
        }
        profiles.create(spec, self.home)
        store = profiles.read_store(self.home)
        self.assertIn("data-analysis", store["custom"])
        self.assertEqual(store["active"], "developer")  # not activated

    def test_create_does_not_activate(self):
        spec = {
            "name": "my-profile",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"],
        }
        profiles.create(spec, self.home)
        self.assertEqual(profiles.load(self.home)["name"], "developer")

    def test_switch_to_custom_after_create(self):
        spec = {
            "name": "my-profile",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"],
        }
        profiles.create(spec, self.home)
        profiles.switch("my-profile", self.home)
        p = profiles.load(self.home)
        self.assertEqual(p["name"], "my-profile")
        self.assertEqual(p["guidance"], profiles.CUSTOM_NOTE)
        self.assertEqual(p["custom"]["purpose"], "Test")

    def test_custom_name_collision_with_builtin(self):
        spec = {
            "name": "developer",
            "purpose": "Override",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"],
        }
        with self.assertRaises(ValueError):
            profiles.create(spec, self.home)

    def test_custom_name_collision_with_existing(self):
        spec = {
            "name": "my-profile",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"],
        }
        profiles.create(spec, self.home)
        with self.assertRaises(ValueError):
            profiles.create(spec, self.home)

    def test_custom_profile_loads_with_custom_guidance(self):
        spec = {
            "name": "my-profile",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"],
        }
        profiles.create(spec, self.home)
        profiles.switch("my-profile", self.home)
        p = profiles.load(self.home)
        self.assertIn("custom_profile", p["guidance"])
        self.assertIn("lower-priority", p["guidance"])


class ValidationTests(ManagedHomeTestCase):
    def test_strict_store_schema(self):
        for store in ({}, {"custom": {}}, {"active": None, "custom": {}},
                      {"active": [], "custom": {}}, {"active": "developer", "custom": []},
                      {"active": "developer", "custom": {}, "extra": True}):
            with self.subTest(store=store), self.assertRaises(ValueError):
                profiles.check_store(store)

    def test_invalid_name_rejected(self):
        for name in ("UPPER", "with space", "with_underscore", "-starts-dash",
                     "", "a" * 40, "12345678901234567890123456789012", "test\n"):
            with self.assertRaises(ValueError):
                profiles.check_name(name)

    def test_valid_names_accepted(self):
        for name in ("my-profile", "a", "data-analysis-2024", "test123"):
            profiles.check_name(name)

    def test_invalid_field_types_rejected(self):
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
                profiles.create(spec, self.home)

    def test_extra_fields_rejected(self):
        spec = {
            "name": "p",
            "purpose": "ok",
            "routine_tasks": ["task"],
            "ask_before": ["action"],
            "extra": "field",
        }
        with self.assertRaises(ValueError):
            profiles.create(spec, self.home)

    def test_missing_fields_rejected(self):
        spec = {"name": "p", "purpose": "ok"}
        with self.assertRaises(ValueError):
            profiles.create(spec, self.home)


class StorageTests(ManagedHomeTestCase):
    def test_symlink_refused(self):
        profiles.switch("browsing", self.home)
        real = profiles.store_path(self.home)
        link = real + ".link"
        os.symlink(real, link)
        os.unlink(real)
        os.symlink(link, real)
        with self.assertRaises(ValueError):
            profiles.switch("developer", self.home)

    def test_oversized_file_rejected(self):
        os.makedirs(profiles.store_dir(self.home), exist_ok=True)
        with open(profiles.store_path(self.home), "w") as f:
            f.write('{"active": "developer", "custom": {}, "extra": "' + "x" * 70000 + '"}')
        with self.assertRaises(ValueError):
            profiles.load(self.home)

    def test_malformed_json_asks(self):
        os.makedirs(profiles.store_dir(self.home), exist_ok=True)
        with open(profiles.store_path(self.home), "w") as f:
            f.write("not json")
        with self.assertRaises(Exception):
            profiles.load(self.home)

    def test_atomic_write_no_data_loss(self):
        profiles.switch("browsing", self.home)
        spec = {
            "name": "test",
            "purpose": "Test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"],
        }
        profiles.create(spec, self.home)
        store = profiles.read_store(self.home)
        self.assertEqual(store["active"], "browsing")
        self.assertIn("test", store["custom"])

    def test_concurrent_creation_serialized(self):
        errors = []
        def create_one(i):
            try:
                spec = {
                    "name": f"profile-{i}",
                    "purpose": f"Purpose {i}",
                    "routine_tasks": [f"Task {i}"],
                    "ask_before": [f"Action {i}"],
                }
                profiles.create(spec, self.home)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=create_one, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(errors), 0)
        store = profiles.read_store(self.home)
        self.assertEqual(len(store["custom"]), 5)

    def test_failed_write_preserves_previous_data(self):
        """Atomic write: if serialization limit fails, previous file is preserved."""
        profiles.switch("browsing", self.home)
        initial = profiles.read_store(self.home)
        self.assertEqual(initial["active"], "browsing")
        huge = {"purpose": "x" * 300, "routine_tasks": ["y" * 200] * 10, "ask_before": ["z" * 200] * 10}
        store = {"active": "developer", "custom": {f"p{i}": huge for i in range(20)}}
        with self.assertRaises(ValueError) as ctx:
            profiles._write(store, self.home)
        self.assertIn("exceeds limit", str(ctx.exception))
        preserved = profiles.read_store(self.home)
        self.assertEqual(preserved["active"], "browsing")

    def test_atomic_replace_failure_preserves_previous_data(self):
        """If os.replace fails during write, previous data is preserved and temp file cleaned."""
        profiles.switch("browsing", self.home)
        store = profiles.read_store(self.home)
        store["active"] = "developer"
        with patch("hooks.profiles.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                profiles._write(store, self.home)
        # Previous file still contains untouched browsing state
        preserved = profiles.read_store(self.home)
        self.assertEqual(preserved["active"], "browsing")
        # Ensure no leftover temporary files in store_dir
        d = profiles.store_dir(self.home)
        leftovers = [f for f in os.listdir(d) if f.startswith(".profiles-")]
        self.assertEqual(leftovers, [])

    def test_duplicate_json_keys_rejected(self):
        os.makedirs(profiles.store_dir(self.home), exist_ok=True)
        with open(profiles.store_path(self.home), "w") as f:
            f.write('{"active": "developer", "active": "browsing", "custom": {}}')
        with self.assertRaises(ValueError) as ctx:
            profiles.load(self.home)
        self.assertIn("duplicate key", str(ctx.exception))

    def test_invalid_utf8_rejected(self):
        os.makedirs(profiles.store_dir(self.home), exist_ok=True)
        with open(profiles.store_path(self.home), "wb") as f:
            f.write(b'{"active": "developer", "custom": {}, "bad": "\xff\xfe"}')
        with self.assertRaises(ValueError) as ctx:
            profiles.load(self.home)
        self.assertIn("UTF-8", str(ctx.exception))

    def test_symlink_tribunal_dir_refused(self):
        claude_dir = os.path.join(self.home, ".claude")
        os.makedirs(claude_dir, exist_ok=True)
        target = os.path.join(self.home, "real_tribunal")
        os.makedirs(target, exist_ok=True)
        tribunal_link = os.path.join(claude_dir, "tribunal")
        os.symlink(target, tribunal_link)
        with self.assertRaises(ValueError) as ctx:
            profiles.read_store(self.home)
        self.assertIn(".claude/tribunal", str(ctx.exception))

    def test_symlink_dot_claude_parent_dir_refused_no_mkdir_side_effects(self):
        """Symlink at ~/.claude must be refused before any mkdir or opens."""
        target = os.path.join(self.home, "real_claude")
        os.makedirs(target, exist_ok=True)
        claude_link = os.path.join(self.home, ".claude")
        os.symlink(target, claude_link)

        # Reading must refuse without creating directories in target
        with self.assertRaises(ValueError) as ctx:
            profiles.read_store(self.home)
        self.assertIn(".claude", str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(target, "tribunal")))

        # Writing/switching must also refuse without creating directories in target
        with self.assertRaises(ValueError) as ctx:
            profiles.switch("browsing", self.home)
        self.assertIn(".claude", str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(target, "tribunal")))

    def test_symlink_lock_refused(self):
        profiles.switch("browsing", self.home)
        lock_path = os.path.join(profiles.store_dir(self.home), ".lock")
        os.unlink(lock_path)
        os.symlink("/tmp/fake-lock", lock_path)
        with self.assertRaises(ValueError):
            profiles.switch("developer", self.home)


class CLITests(ManagedHomeTestCase):
    def test_list_shows_builtins(self):
        proc, _ = self.run_cli(["list"])
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["active"], "developer")
        self.assertEqual(set(out["builtin"]), {"developer", "office-design", "browsing"})
        self.assertEqual(out["custom"], {})

    def test_show_active(self):
        proc, _ = self.run_cli(["show"])
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["active"], "developer")

    def test_switch_builtin(self):
        proc, _ = self.run_cli(["switch", "browsing"])
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["active"], "browsing")
        proc2, _ = self.run_cli(["show"])
        self.assertEqual(json.loads(proc2.stdout)["active"], "browsing")

    def test_switch_unknown_fails(self):
        proc, _ = self.run_cli(["switch", "nonexistent"])
        self.assertNotEqual(proc.returncode, 0)

    def test_create_from_stdin(self):
        spec = {
            "name": "cli-profile",
            "purpose": "CLI test",
            "routine_tasks": ["Task"],
            "ask_before": ["Action"],
        }
        proc, _ = self.run_cli(["create"], json.dumps(spec))
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["created"], "cli-profile")
        self.assertEqual(out["active"], "developer")

    def test_create_invalid_stdin_fails(self):
        proc, _ = self.run_cli(["create"], json.dumps({"name": "bad"}))
        self.assertNotEqual(proc.returncode, 0)

    def test_create_stdin_duplicate_keys_fails(self):
        raw = '{"name": "p", "name": "p2", "purpose": "ok", "routine_tasks": ["a"], "ask_before": ["b"]}'
        proc, _ = self.run_cli(["create"], raw)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("duplicate key", proc.stderr.lower())

    def test_create_stdin_oversized_multibyte_fails(self):
        spec = {
            "name": "p",
            "purpose": "ok",
            "routine_tasks": ["task"],
            "ask_before": ["action"],
            "padding": "🔥" * 20000,
        }
        proc, _ = self.run_cli(["create"], json.dumps(spec, ensure_ascii=False))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("too large", proc.stderr.lower())

    def test_fifo_rejection_without_hang(self):
        d = profiles.store_dir(self.home)
        os.makedirs(d, mode=0o700, exist_ok=True)
        fifo_path = profiles.store_path(self.home)
        os.mkfifo(fifo_path)
        proc, _ = self.run_cli(["show"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not a regular file", proc.stderr)
        os.unlink(fifo_path)

    def test_create_preserves_shell_metacharacters_as_data(self):
        spec = {"name": "quoted", "purpose": "User's $(touch nope); `uname`",
                "routine_tasks": ["Export local files"], "ask_before": ["Uploads"]}
        script = os.path.join(self.home, "plugin with spaces", "profiles.py")
        os.makedirs(os.path.dirname(script))
        import shutil
        shutil.copyfile(SCRIPT, script)
        proc = subprocess.run([sys.executable, "-I", script, "create"],
                              input=json.dumps(spec), capture_output=True, text=True,
                              env=clean_env(self.home), cwd=self.home, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(profiles.read_store(self.home)["custom"]["quoted"]["purpose"], spec["purpose"])
        self.assertFalse(os.path.exists(os.path.join(self.home, "nope")))

    def test_skills_require_explicit_invocation_and_data_transport(self):
        for name in ("profile", "create-profile"):
            text = (ROOT / "skills" / name / "SKILL.md").read_text()
            self.assertIn("disable-model-invocation: true", text)
            self.assertIn('"${CLAUDE_PLUGIN_ROOT}/hooks/profiles.py"', text)
        text = (ROOT / "skills/create-profile/SKILL.md").read_text()
        self.assertIn("Show the exact JSON", text)
        self.assertIn("Activate separately", text)
        self.assertIn("use Write", text)
        self.assertNotIn("echo '<json>' |", text)

    def test_no_args_shows_usage(self):
        proc, _ = self.run_cli([])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("usage", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
