"""Held-out tests for palindrome(s)."""

import unittest

from solution import palindrome


class PalindromeTests(unittest.TestCase):
    """Verify palindrome(s) held-out cases."""

    def test_abba(self) -> None:
        """Verify the abba case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(palindrome("abba"))

    def test_abc(self) -> None:
        """Verify the abc case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertFalse(palindrome("abc"))

    def test_single(self) -> None:
        """Verify the single case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(palindrome("a"))


if __name__ == "__main__":
    unittest.main()
