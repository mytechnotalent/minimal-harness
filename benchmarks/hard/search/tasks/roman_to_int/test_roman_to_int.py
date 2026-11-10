"""roman_to_int tests."""

import unittest

from solution import roman_to_int


class RomanToIntTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_four(self) -> None:
        """Verify the four case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(roman_to_int("IV"), 4)

    def test_nine(self) -> None:
        """Verify the nine case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(roman_to_int("IX"), 9)

    def test_full(self) -> None:
        """Verify the full case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(roman_to_int("MCMXCIV"), 1994)


if __name__ == "__main__":
    unittest.main()
