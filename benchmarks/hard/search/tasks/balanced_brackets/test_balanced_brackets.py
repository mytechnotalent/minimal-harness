"""balanced_brackets tests."""

import unittest

from solution import balanced_brackets


class BalancedBracketsTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_simple(self) -> None:
        """Verify the simple case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(balanced_brackets("()"))

    def test_mismatch(self) -> None:
        """Verify the mismatch case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertFalse(balanced_brackets("(]"))

    def test_nested(self) -> None:
        """Verify the nested case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(balanced_brackets("([{}])"))


if __name__ == "__main__":
    unittest.main()
