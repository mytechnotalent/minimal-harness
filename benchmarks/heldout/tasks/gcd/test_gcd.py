"""Held-out tests for gcd(a, b)."""

import unittest

from solution import gcd


class GcdTests(unittest.TestCase):
    """Verify gcd(a, b) held-out cases."""

    def test_common(self) -> None:
        """Verify the common case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(gcd(48, 18), 6)

    def test_coprime(self) -> None:
        """Verify the coprime case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(gcd(9, 28), 1)

    def test_zeros(self) -> None:
        """Verify the zeros case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(gcd(0, 0), 0)


if __name__ == "__main__":
    unittest.main()
