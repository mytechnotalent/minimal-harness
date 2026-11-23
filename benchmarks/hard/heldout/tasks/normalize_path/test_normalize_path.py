"""normalize_path tests."""

import unittest

from solution import normalize_path


class NormalizePathTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_absolute_parent(self) -> None:
        """Verify the absolute_parent case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(normalize_path("/a/../../b"), "/b")

    def test_repeated(self) -> None:
        """Verify the repeated case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(normalize_path("a//b//"), "a/b")

    def test_leading_parent(self) -> None:
        """Verify the leading_parent case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(normalize_path("../a"), "../a")

    def test_relative_parent(self) -> None:
        """Verify the relative_parent case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(normalize_path("a/../../b"), "../b")


if __name__ == "__main__":
    unittest.main()
