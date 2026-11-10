"""Validation tests for fibonacci(n)."""

import unittest

from solution import fibonacci


class FibonacciTests(unittest.TestCase):
    """Verify fibonacci(n) validation cases."""

    def test_zero(self) -> None:
        """Verify the zero case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fibonacci(0), 0)

    def test_five(self) -> None:
        """Verify the five case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fibonacci(5), 5)

    def test_twelve(self) -> None:
        """Verify the twelve case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fibonacci(12), 144)


if __name__ == "__main__":
    unittest.main()
