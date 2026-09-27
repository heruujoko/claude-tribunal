import unittest

from hooks.validator import map_answer


class MapAnswerTests(unittest.TestCase):
    def setUp(self):
        self.min = 0.5

    def test_allowed(self):
        a = {"type": "choice", "choice": "allowed", "confidence": 0.93}
        self.assertEqual(map_answer(a, self.min), "allow")

    def test_rejected(self):
        a = {"type": "choice", "choice": "rejected", "confidence": 0.9}
        self.assertEqual(map_answer(a, self.min), "deny")

    def test_human_ask(self):
        a = {"type": "choice", "choice": "human_ask", "confidence": 0.8}
        self.assertEqual(map_answer(a, self.min), "ask")

    def test_low_confidence_becomes_ask(self):
        a = {"type": "choice", "choice": "allowed", "confidence": 0.3}
        self.assertEqual(map_answer(a, self.min), "ask")

    def test_low_confidence_deny_also_asks(self):
        a = {"type": "choice", "choice": "rejected", "confidence": 0.2}
        self.assertEqual(map_answer(a, self.min), "ask")

    def test_unknown_choice_is_none(self):
        self.assertIsNone(map_answer({"type": "choice", "choice": "yes", "confidence": 0.9}, self.min))

    def test_missing_choice_is_none(self):
        self.assertIsNone(map_answer({"type": "choice", "confidence": 0.9}, self.min))

    def test_missing_confidence_asks(self):
        self.assertEqual(map_answer({"type": "choice", "choice": "allowed"}, self.min), "ask")

    def test_invalid_confidence_asks(self):
        for value in ("0.99", True, float("nan"), 1.5):
            with self.subTest(value=value):
                self.assertEqual(map_answer({"type": "choice", "choice": "allowed", "confidence": value}, self.min), "ask")

    def test_non_choice_answer_asks(self):
        self.assertIsNone(map_answer({"type": "score", "choice": "allowed",
                                      "confidence": 0.99}, self.min))


if __name__ == "__main__":
    unittest.main()
