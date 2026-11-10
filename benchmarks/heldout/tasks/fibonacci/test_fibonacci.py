"""Held-out tests for fibonacci(n)."""

import unittest

from solution import fibonacci


class FibonacciTests(unittest.TestCase):
    """Verify fibonacci(n) held-out cases."""

    def test_two(self) -> None:
        """Verify the two case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fibonacci(2), 1)

    def test_seven(self) -> None:
        """Verify the seven case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fibonacci(7), 13)

    def test_fifteen(self) -> None:
        """Verify the fifteen case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fibonacci(15), 610)


if __name__ == "__main__":
    unittest.main()
