"""Held-out tests for sum_list(xs)."""

import unittest

from solution import sum_list


class SumListTests(unittest.TestCase):
    """Verify sum_list(xs) held-out cases."""

    def test_single(self) -> None:
        """Verify the single case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(sum_list([5]), 5)

    def test_cancel(self) -> None:
        """Verify the cancel case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(sum_list([10, -10]), 0)

    def test_four(self) -> None:
        """Verify the four case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(sum_list([1, 2, 3, 4]), 10)


if __name__ == "__main__":
    unittest.main()
