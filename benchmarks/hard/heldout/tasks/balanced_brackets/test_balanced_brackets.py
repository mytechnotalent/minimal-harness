"""balanced_brackets tests."""

import unittest

from solution import balanced_brackets


class BalancedBracketsTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_interleaved(self) -> None:
        """Verify the interleaved case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertFalse(balanced_brackets("([)]"))

    def test_unclosed(self) -> None:
        """Verify the unclosed case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertFalse(balanced_brackets("(((("))

    def test_sequence(self) -> None:
        """Verify the sequence case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(balanced_brackets("{}[]()"))


if __name__ == "__main__":
    unittest.main()
