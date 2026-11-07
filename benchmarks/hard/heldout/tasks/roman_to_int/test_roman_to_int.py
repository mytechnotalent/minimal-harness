"""roman_to_int tests."""

import unittest

from solution import roman_to_int


class RomanToIntTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_year(self) -> None:
        """Verify the year case."""
        self.assertEqual(roman_to_int("MMXXIV"), 2024)

    def test_four_hundred(self) -> None:
        """Verify the four_hundred case."""
        self.assertEqual(roman_to_int("CD"), 400)

    def test_nine_hundred(self) -> None:
        """Verify the nine_hundred case."""
        self.assertEqual(roman_to_int("CM"), 900)

    def test_ninety(self) -> None:
        """Verify the ninety case."""
        self.assertEqual(roman_to_int("XC"), 90)


if __name__ == "__main__":
    unittest.main()
