"""Held-out tests for double(x)."""

import unittest

from solution import double


class DoubleTests(unittest.TestCase):
    """Verify double(x) held-out cases."""

    def test_ten(self) -> None:
        """Verify the ten case."""
        self.assertEqual(double(10), 20)

    def test_negative(self) -> None:
        """Verify the negative case."""
        self.assertEqual(double(-1), -2)

    def test_fraction(self) -> None:
        """Verify the fraction case."""
        self.assertEqual(double(2.5), 5.0)


if __name__ == "__main__":
    unittest.main()
