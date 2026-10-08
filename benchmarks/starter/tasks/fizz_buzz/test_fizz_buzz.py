"""Tests for the fizz_buzz(n) starter task."""

import unittest

from solution import fizz_buzz


class FizzBuzzTests(unittest.TestCase):
    """Verify fizz_buzz(n) returns the classic sequence."""

    def test_three(self) -> None:
        """fizz_buzz(3) is ['1', '2', 'Fizz']."""
        self.assertEqual(fizz_buzz(3), ["1", "2", "Fizz"])

    def test_five(self) -> None:
        """fizz_buzz(5) ends with 'Buzz'."""
        self.assertEqual(fizz_buzz(5)[-1], "Buzz")

    def test_fifteen(self) -> None:
        """fizz_buzz(15) ends with 'FizzBuzz'."""
        self.assertEqual(fizz_buzz(15)[-1], "FizzBuzz")


if __name__ == "__main__":
    unittest.main()
