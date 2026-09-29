import time
import unittest

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


if __name__ == "__main__":
    unittest.main()
