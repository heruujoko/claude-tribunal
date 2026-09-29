import unittest

from hooks import tribunal


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


if __name__ == "__main__":
    unittest.main()
