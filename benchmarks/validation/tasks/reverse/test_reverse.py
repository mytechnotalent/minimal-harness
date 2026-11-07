"""Validation tests for reverse(s)."""

import unittest

from solution import reverse


class ReverseTests(unittest.TestCase):
    """Verify reverse(s) validation cases."""

    def test_five(self) -> None:
        """Verify the five case."""
        self.assertEqual(reverse("abcde"), "edcba")

    def test_double(self) -> None:
        """Verify the double case."""
        self.assertEqual(reverse("aa"), "aa")

    def test_digit(self) -> None:
        """Verify the digit case."""
        self.assertEqual(reverse("1"), "1")


if __name__ == "__main__":
    unittest.main()
