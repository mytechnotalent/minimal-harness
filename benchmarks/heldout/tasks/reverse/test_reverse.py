"""Held-out tests for reverse(s)."""

import unittest

from solution import reverse


class ReverseTests(unittest.TestCase):
    """Verify reverse(s) held-out cases."""

    def test_abc(self) -> None:
        """Verify the abc case."""
        self.assertEqual(reverse("abc"), "cba")

    def test_single(self) -> None:
        """Verify the single case."""
        self.assertEqual(reverse("x"), "x")

    def test_two(self) -> None:
        """Verify the two case."""
        self.assertEqual(reverse("ab"), "ba")


if __name__ == "__main__":
    unittest.main()
