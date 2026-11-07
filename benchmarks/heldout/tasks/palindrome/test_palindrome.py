"""Held-out tests for palindrome(s)."""

import unittest

from solution import palindrome


class PalindromeTests(unittest.TestCase):
    """Verify palindrome(s) held-out cases."""

    def test_abba(self) -> None:
        """Verify the abba case."""
        self.assertTrue(palindrome("abba"))

    def test_abc(self) -> None:
        """Verify the abc case."""
        self.assertFalse(palindrome("abc"))

    def test_single(self) -> None:
        """Verify the single case."""
        self.assertTrue(palindrome("a"))


if __name__ == "__main__":
    unittest.main()
