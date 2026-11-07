"""Validation tests for gcd(a, b)."""

import unittest

from solution import gcd


class GcdTests(unittest.TestCase):
    """Verify gcd(a, b) validation cases."""

    def test_coprime(self) -> None:
        """Verify the coprime case."""
        self.assertEqual(gcd(7, 13), 1)

    def test_common(self) -> None:
        """Verify the common case."""
        self.assertEqual(gcd(100, 75), 25)

    def test_zero(self) -> None:
        """Verify the zero case."""
        self.assertEqual(gcd(0, 5), 5)


if __name__ == "__main__":
    unittest.main()
