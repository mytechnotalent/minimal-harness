"""Tests for the gcd(a, b) starter task."""

import unittest

from solution import gcd


class GcdTests(unittest.TestCase):
    """Verify gcd(a, b) returns the greatest common divisor."""

    def test_coprime(self) -> None:
        """gcd(8, 9) is 1."""
        self.assertEqual(gcd(8, 9), 1)

    def test_common_factor(self) -> None:
        """gcd(12, 18) is 6."""
        self.assertEqual(gcd(12, 18), 6)

    def test_zero(self) -> None:
        """gcd(0, 7) is 7."""
        self.assertEqual(gcd(0, 7), 7)


if __name__ == "__main__":
    unittest.main()
