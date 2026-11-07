"""Validation tests for sum_list(xs)."""

import unittest

from solution import sum_list


class SumListTests(unittest.TestCase):
    """Verify sum_list(xs) validation cases."""

    def test_empty(self) -> None:
        """Verify the empty case."""
        self.assertEqual(sum_list([]), 0)

    def test_seven(self) -> None:
        """Verify the seven case."""
        self.assertEqual(sum_list([7]), 7)

    def test_mixed(self) -> None:
        """Verify the mixed case."""
        self.assertEqual(sum_list([-2, 2, 5]), 5)


if __name__ == "__main__":
    unittest.main()
