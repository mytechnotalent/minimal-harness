"""Tests for the is_even(x) starter task."""

import unittest

from solution import is_even


class IsEvenTests(unittest.TestCase):
    """Verify is_even(x) reports evenness."""

    def test_four(self) -> None:
        """is_even(4) is True."""
        self.assertTrue(is_even(4))

    def test_seven(self) -> None:
        """is_even(7) is False."""
        self.assertFalse(is_even(7))

    def test_zero(self) -> None:
        """is_even(0) is True."""
        self.assertTrue(is_even(0))


if __name__ == "__main__":
    unittest.main()
