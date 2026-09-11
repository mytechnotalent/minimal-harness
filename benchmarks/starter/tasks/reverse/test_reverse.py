"""Tests for the reverse(s) starter task."""

import unittest

from solution import reverse


class ReverseTests(unittest.TestCase):
    """Verify reverse(s) reverses a string."""

    def test_hello(self) -> None:
        """reverse('hello') is 'olleh'."""
        self.assertEqual(reverse("hello"), "olleh")

    def test_empty(self) -> None:
        """reverse('') is ''."""
        self.assertEqual(reverse(""), "")

    def test_palindrome(self) -> None:
        """reverse('abba') is 'abba'."""
        self.assertEqual(reverse("abba"), "abba")


if __name__ == "__main__":
    unittest.main()
