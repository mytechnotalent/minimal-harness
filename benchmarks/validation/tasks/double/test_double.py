"""Validation tests for double(x)."""

import unittest

from solution import double


class DoubleTests(unittest.TestCase):
    """Verify double(x) validation cases."""

    def test_three(self) -> None:
        """Verify the three case."""
        self.assertEqual(double(3), 6)

    def test_negative(self) -> None:
        """Verify the negative case."""
        self.assertEqual(double(-7), -14)

    def test_half(self) -> None:
        """Verify the half case."""
        self.assertEqual(double(0.5), 1.0)


if __name__ == "__main__":
    unittest.main()
