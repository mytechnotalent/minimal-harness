"""Validation tests for is_even(x)."""

import unittest

from solution import is_even


class IsEvenTests(unittest.TestCase):
    """Verify is_even(x) validation cases."""

    def test_zero(self) -> None:
        """Verify the zero case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(is_even(0))

    def test_one(self) -> None:
        """Verify the one case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertFalse(is_even(1))

    def test_negative(self) -> None:
        """Verify the negative case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(is_even(-2))


if __name__ == "__main__":
    unittest.main()
