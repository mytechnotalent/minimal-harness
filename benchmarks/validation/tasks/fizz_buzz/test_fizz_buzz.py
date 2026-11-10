"""Validation tests for fizz_buzz(n)."""

import unittest

from solution import fizz_buzz


class FizzBuzzTests(unittest.TestCase):
    """Verify fizz_buzz(n) validation cases."""

    def test_three(self) -> None:
        """Verify the three case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fizz_buzz(3)[-1], "Fizz")

    def test_five(self) -> None:
        """Verify the five case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fizz_buzz(5)[-1], "Buzz")

    def test_fifteen(self) -> None:
        """Verify the fifteen case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fizz_buzz(15)[-1], "FizzBuzz")

    def test_two(self) -> None:
        """Verify the two case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fizz_buzz(2), ["1", "2"])


if __name__ == "__main__":
    unittest.main()
