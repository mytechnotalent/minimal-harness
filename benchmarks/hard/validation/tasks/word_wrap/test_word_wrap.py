"""word_wrap tests."""

import unittest

from solution import word_wrap


class WordWrapTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_empty(self) -> None:
        """Verify the empty case."""
        self.assertEqual(word_wrap("", 5), [])

    def test_one(self) -> None:
        """Verify the one case."""
        self.assertEqual(word_wrap("a b c", 1), ["a", "b", "c"])

    def test_long_word(self) -> None:
        """Verify the long_word case."""
        self.assertEqual(word_wrap("abcdef", 3), ["abcdef"])

    def test_hello(self) -> None:
        """Verify the hello case."""
        self.assertEqual(word_wrap("hello world", 5), ["hello", "world"])


if __name__ == "__main__":
    unittest.main()
