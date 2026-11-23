"""Held-out tests for is_even(x)."""

import unittest

from solution import is_even


class IsEvenTests(unittest.TestCase):
    """Verify is_even(x) held-out cases."""

    def test_two(self) -> None:
        """Verify the two case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(is_even(2))

    def test_three(self) -> None:
        """Verify the three case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertFalse(is_even(3))

    def test_negative(self) -> None:
        """Verify the negative case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(is_even(-4))


if __name__ == "__main__":
    unittest.main()
