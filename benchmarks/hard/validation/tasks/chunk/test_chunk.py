"""chunk tests."""

import unittest

from solution import chunk


class ChunkTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_empty(self) -> None:
        """Verify the empty case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(chunk([], 1), [])

    def test_single(self) -> None:
        """Verify the single case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(chunk([1], 1), [[1]])

    def test_zero(self) -> None:
        """Verify the zero case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with self.assertRaises(ValueError):
            chunk([1], 0)

    def test_negative(self) -> None:
        """Verify the negative case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with self.assertRaises(ValueError):
            chunk([1], -1)


if __name__ == "__main__":
    unittest.main()
