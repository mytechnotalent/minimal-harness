"""Held-out tests for fizz_buzz(n)."""

import unittest

from solution import fizz_buzz


class FizzBuzzTests(unittest.TestCase):
    """Verify fizz_buzz(n) held-out cases."""

    def test_one(self) -> None:
        """Verify the one case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fizz_buzz(1), ["1"])

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

    def test_six(self) -> None:
        """Verify the six case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fizz_buzz(6)[-1], "Fizz")

    def test_thirty(self) -> None:
        """Verify the thirty case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(fizz_buzz(30)[-1], "FizzBuzz")


if __name__ == "__main__":
    unittest.main()
