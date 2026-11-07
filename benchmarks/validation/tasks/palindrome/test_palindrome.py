"""Validation tests for palindrome(s)."""

import unittest

from solution import palindrome


class PalindromeTests(unittest.TestCase):
    """Verify palindrome(s) validation cases."""

    def test_level(self) -> None:
        """Verify the level case."""
        self.assertTrue(palindrome("level"))

    def test_plural(self) -> None:
        """Verify the plural case."""
        self.assertFalse(palindrome("levels"))

    def test_double(self) -> None:
        """Verify the double case."""
        self.assertTrue(palindrome("aa"))


if __name__ == "__main__":
    unittest.main()
