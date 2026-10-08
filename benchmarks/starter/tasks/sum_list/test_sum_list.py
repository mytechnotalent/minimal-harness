"""Tests for the sum_list(xs) starter task."""

import unittest

from solution import sum_list


class SumListTests(unittest.TestCase):
    """Verify sum_list(xs) totals a list of numbers."""

    def test_ints(self) -> None:
        """sum_list([1, 2, 3]) is 6."""
        self.assertEqual(sum_list([1, 2, 3]), 6)

    def test_empty(self) -> None:
        """sum_list([]) is 0."""
        self.assertEqual(sum_list([]), 0)

    def test_negative(self) -> None:
        """sum_list([-1, -2, 3]) is 0."""
        self.assertEqual(sum_list([-1, -2, 3]), 0)


if __name__ == "__main__":
    unittest.main()
