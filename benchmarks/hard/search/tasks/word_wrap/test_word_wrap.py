"""word_wrap tests."""

import unittest

from solution import word_wrap


class WordWrapTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_fox(self) -> None:
        """Verify the fox case."""
        self.assertEqual(
            word_wrap("the quick brown fox", 10), ["the quick", "brown fox"]
        )

    def test_three(self) -> None:
        """Verify the three case."""
        self.assertEqual(
            word_wrap("one two three", 5), ["one", "two", "three"]
        )


if __name__ == "__main__":
    unittest.main()
