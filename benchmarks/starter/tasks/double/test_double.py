"""Tests for the double(x) starter task."""

import unittest

from solution import double


class DoubleTests(unittest.TestCase):
    """Verify double(x) returns twice its input."""

    def test_two(self) -> None:
        """double(2) is 4."""
        self.assertEqual(double(2), 4)

    def test_zero(self) -> None:
        """double(0) is 0."""
        self.assertEqual(double(0), 0)

    def test_negative(self) -> None:
        """double(-3) is -6."""
        self.assertEqual(double(-3), -6)


if __name__ == "__main__":
    unittest.main()
