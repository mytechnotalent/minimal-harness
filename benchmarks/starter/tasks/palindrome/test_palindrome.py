"""Tests for the palindrome(s) starter task."""

import unittest

from solution import palindrome


class PalindromeTests(unittest.TestCase):
    """Verify palindrome(s) detects reversible strings."""

    def test_racecar(self) -> None:
        """palindrome('racecar') is True."""
        self.assertTrue(palindrome("racecar"))

    def test_hello(self) -> None:
        """palindrome('hello') is False."""
        self.assertFalse(palindrome("hello"))

    def test_empty(self) -> None:
        """palindrome('') is True."""
        self.assertTrue(palindrome(""))


if __name__ == "__main__":
    unittest.main()
