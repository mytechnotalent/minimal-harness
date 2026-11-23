"""roman_to_int tests."""

import unittest

from solution import roman_to_int


class RomanToIntTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_three(self) -> None:
        """Verify the three case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(roman_to_int("III"), 3)

    def test_fifty_eight(self) -> None:
        """Verify the fifty_eight case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(roman_to_int("LVIII"), 58)

    def test_forty(self) -> None:
        """Verify the forty case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(roman_to_int("XL"), 40)

    def test_invalid(self) -> None:
        """Verify the invalid case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with self.assertRaises(ValueError):
            roman_to_int("ABC")

    def test_empty(self) -> None:
        """Verify the empty case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with self.assertRaises(ValueError):
            roman_to_int("")


if __name__ == "__main__":
    unittest.main()
