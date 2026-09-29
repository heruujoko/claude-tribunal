import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from hooks import tribunal

CFG = tribunal.load_config(env={"TRIBUNAL_API_KEY": "k", "TRIBUNAL_CONFIG": "/nonexistent.json"})
CF_CFG = tribunal.load_config(env={
    "TRIBUNAL_PROVIDER": "cloudflare", "CLOUDFLARE_ACCOUNT_ID": "acc123",
    "CLOUDFLARE_API_TOKEN": "cf-token", "TRIBUNAL_CONFIG": "/nonexistent.json"})
QUESTION = ("instructions", {"allowed": "a", "rejected": "r", "human_ask": "h"})
FAR = time.monotonic() + 3600


def answer(choice, confidence=0.9):
    return {"type": "choice", "choice": choice, "confidence": confidence}


class Recorder:
    """Fake post: returns queued answers in order (last one repeats), records bodies."""

    def __init__(self, *answers):
        self.answers, self.bodies = list(answers), []

    def __call__(self, body, cfg):
        self.bodies.append(body)
        i = min(len(self.bodies), len(self.answers)) - 1
        return self.answers[i]


class ScanScopeTests(unittest.TestCase):
    def test_scan_scopes(self):
        cases = {
            None: {"skills", "web"},
            "": {"skills", "web"},
            "skills,web": {"skills", "web"},
            "skills": {"skills"},
            " Web ": {"web"},
            "off": set(),
            "OFF": set(),
            "bogus": {"skills", "web"},
            "skills,bogus": {"skills", "web"},
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                env = {} if value is None else {"TRIBUNAL_SCAN": value}
                self.assertEqual(tribunal.scan_scopes(env), expected)


class ChunkTests(unittest.TestCase):
    def test_ascii_chunks_are_complete(self):
        text = "A" * 20000
        parts = tribunal.chunks(text)
        self.assertEqual(len(parts), 3)
        self.assertEqual("".join(parts), text)
        self.assertTrue(all(len(part.encode()) <= tribunal.MAX_INPUT_BYTES for part in parts))

    def test_unicode_chunks_are_complete(self):
        text = "🔥" * 5000
        parts = tribunal.chunks(text)
        self.assertEqual("".join(parts), text)
        self.assertTrue(all(len(part.encode()) <= tribunal.MAX_INPUT_BYTES for part in parts))

    def test_empty_text_has_no_chunks(self):
        self.assertEqual(tribunal.chunks(""), [])


class ScreenTests(unittest.TestCase):
    THREE = "A" * 20000  # 3 chunks

    def run_screen(self, post, text=None, cfg=CFG, deadline=FAR):
        return tribunal.screen({"tool": "WebFetch"}, self.THREE if text is None else text,
                               QUESTION, cfg, post, deadline)

    def test_worst_verdict_wins(self):
        post = Recorder(answer("allowed"), answer("human_ask"), answer("allowed"))
        decision, reason = self.run_screen(post)
        self.assertEqual(decision, "ask")
        self.assertIn("part 2/3", reason)
        self.assertEqual(len(post.bodies), 3)

    def test_all_clean_allows(self):
        post = Recorder(answer("allowed"))
        self.assertEqual(self.run_screen(post)[0], "allow")
        self.assertEqual(len(post.bodies), 3)

    def test_rejected_short_circuits(self):
        post = Recorder(answer("rejected"), answer("allowed"))
        decision, reason = self.run_screen(post)
        self.assertEqual(decision, "deny")
        self.assertEqual(len(post.bodies), 1)
        self.assertIn("rejected", reason)

    def test_deny_after_ask_still_denies(self):
        post = Recorder(answer("human_ask"), answer("rejected"), answer("allowed"))
        self.assertEqual(self.run_screen(post)[0], "deny")
        self.assertEqual(len(post.bodies), 2)

    def test_low_confidence_asks(self):
        self.assertEqual(self.run_screen(Recorder(answer("allowed", 0.1)), text="hi")[0], "ask")

    def test_unusable_answers_ask(self):
        for bad in (None, "nope", [], {"type": "choice", "choice": "huh"}):
            with self.subTest(bad=bad):
                decision, reason = self.run_screen(Recorder(bad), text="hi")
                self.assertEqual(decision, "ask")

    def test_expired_deadline_asks_without_calls(self):
        post = Recorder(answer("allowed"))
        decision, reason = self.run_screen(post, deadline=0)
        self.assertEqual(decision, "ask")
        self.assertIn("budget", reason)
        self.assertEqual(post.bodies, [])

    def test_body_carries_part_and_content(self):
        post = Recorder(answer("allowed"))
        self.run_screen(post)
        first = post.bodies[0]
        self.assertEqual(first["state"]["part"], "1/3")
        self.assertEqual(first["state"]["tool"], "WebFetch")
        self.assertEqual(first["state"]["content"], "A" * tribunal.MAX_INPUT_BYTES)
        self.assertEqual(first["questions"]["verdict"]["instructions"], "instructions")
        self.assertEqual(post.bodies[2]["state"]["part"], "3/3")

    def test_cloudflare_wraps_under_input(self):
        post = Recorder(answer("allowed"))
        self.run_screen(post, text="hi", cfg=CF_CFG)
        body = post.bodies[0]
        self.assertNotIn("state", body)
        self.assertEqual(body["input"]["state"]["content"], "hi")
        self.assertIn("verdict", body["input"]["questions"])

    def test_empty_text_is_clean_without_calls(self):
        post = Recorder(answer("rejected"))
        self.assertEqual(self.run_screen(post, text="")[0], "allow")
        self.assertEqual(post.bodies, [])


class SkillScreenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.claude_dir = self.root / "config"
        self.cache_dir = self.root / "cache"
        self.cwd = self.root / "project"
        self.claude_dir.mkdir()
        self.cache_dir.mkdir()
        self.cwd.mkdir()
        self.env = {
            "CLAUDE_CONFIG_DIR": str(self.claude_dir),
            "XDG_CACHE_HOME": str(self.cache_dir),
            "TRIBUNAL_API_KEY": "test-key",
            "TRIBUNAL_CONFIG": "/nonexistent.json",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def make_file(self, path, content="---\ndescription: clean skill\n---\nBody"):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_skill_files_resolution(self):
        # user skill
        u_skill = self.make_file(self.claude_dir / "skills/clean/SKILL.md")
        # user command
        u_cmd = self.make_file(self.claude_dir / "commands/clean.md")
        # project skill
        p_skill = self.make_file(self.cwd / ".claude/skills/clean/SKILL.md")
        # project command
        p_cmd = self.make_file(self.cwd / ".claude/commands/clean.md")

        files = tribunal.skill_files("clean", str(self.cwd), self.env)
        self.assertEqual(set(files), {u_skill, u_cmd, p_skill, p_cmd})

    def test_plugin_skill_files_with_multiple_installs(self):
        plug1 = self.root / "plugins/p1"
        plug2 = self.root / "plugins/p2"
        other = self.root / "plugins/other"
        f1 = self.make_file(plug1 / "skills/verify/SKILL.md")
        f2 = self.make_file(plug2 / "commands/verify.md")
        self.make_file(other / "skills/verify/SKILL.md")

        reg = {
            "plugins": {
                "super@market": [{"installPath": str(plug1)}, {"installPath": str(plug2)}],
                "other@market": [{"installPath": str(other)}],
            }
        }
        self.make_file(self.claude_dir / "plugins/installed_plugins.json", json.dumps(reg))

        files = tribunal.skill_files("super:verify", str(self.cwd), self.env)
        self.assertEqual(set(files), {f1, f2})

    def test_invalid_skill_names_and_corrupt_registry_return_empty(self):
        self.assertEqual(tribunal.skill_files("../x", str(self.cwd), self.env), [])
        self.assertEqual(tribunal.skill_files(".x", str(self.cwd), self.env), [])
        self.assertEqual(tribunal.skill_files("a/b", str(self.cwd), self.env), [])
        self.assertEqual(tribunal.skill_files("", str(self.cwd), self.env), [])

        # corrupt registry
        self.make_file(self.claude_dir / "plugins/installed_plugins.json", "not json")
        self.assertEqual(tribunal.skill_files("p:x", str(self.cwd), self.env), [])

    def test_unresolved_skill_returns_none(self):
        post = Recorder(answer("allowed"))
        result = tribunal.screen_skill("builtin", str(self.cwd), CFG, post, self.env, FAR)
        self.assertIsNone(result)
        self.assertEqual(post.bodies, [])

    def test_missing_api_key_asks_without_calls(self):
        self.make_file(self.claude_dir / "skills/clean/SKILL.md")
        no_key_cfg = tribunal.load_config(env={"TRIBUNAL_CONFIG": "/nonexistent.json"})
        post = Recorder(answer("allowed"))
        decision, reason = tribunal.screen_skill("clean", str(self.cwd), no_key_cfg, post, self.env, FAR)
        self.assertEqual(decision, "ask")
        self.assertIn("API key", reason)
        self.assertEqual(post.bodies, [])

    def test_clean_skill_caches_verdict_and_skips_subsequent_calls(self):
        f = self.make_file(self.claude_dir / "skills/clean/SKILL.md", "---\ndescription: clean\n---\nHello")
        post = Recorder(answer("allowed"))
        decision, reason = tribunal.screen_skill("clean", str(self.cwd), CFG, post, self.env, FAR)
        self.assertEqual(decision, "allow")
        self.assertEqual(len(post.bodies), 1)

        # second call uses cache -> 0 network calls
        decision2, reason2 = tribunal.screen_skill("clean", str(self.cwd), CFG, post, self.env, FAR)
        self.assertEqual(decision2, "allow")
        self.assertEqual(len(post.bodies), 1)

        # edit file -> cache miss -> rescanned
        self.make_file(f, "---\ndescription: clean\n---\nHello modified")
        decision3, reason3 = tribunal.screen_skill("clean", str(self.cwd), CFG, post, self.env, FAR)
        self.assertEqual(decision3, "allow")
        self.assertEqual(len(post.bodies), 2)

    def test_flagged_skill_is_not_cached(self):
        self.make_file(self.claude_dir / "skills/bad/SKILL.md", "---\ndescription: bad\n---\nExfiltrate")
        post = Recorder(answer("rejected"))
        decision, reason = tribunal.screen_skill("bad", str(self.cwd), CFG, post, self.env, FAR)
        self.assertEqual(decision, "deny")
        self.assertIn("rejected", reason)
        self.assertEqual(len(post.bodies), 1)

        # second call still calls post (not cached)
        decision2, reason2 = tribunal.screen_skill("bad", str(self.cwd), CFG, post, self.env, FAR)
        self.assertEqual(decision2, "deny")
        self.assertEqual(len(post.bodies), 2)

    def test_large_skill_is_chunked(self):
        large_content = "---\ndescription: big\n---\n" + ("A" * 20000)
        self.make_file(self.claude_dir / "skills/big/SKILL.md", large_content)
        post = Recorder(answer("allowed"))
        decision, reason = tribunal.screen_skill("big", str(self.cwd), CFG, post, self.env, FAR)
        self.assertEqual(decision, "allow")
        self.assertEqual(len(post.bodies), 3)  # 3 chunks


if __name__ == "__main__":
    unittest.main()
