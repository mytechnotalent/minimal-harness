"""normalize_path tests."""

import unittest

from solution import normalize_path


class NormalizePathTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_root_parent(self) -> None:
        """Verify the root_parent case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(normalize_path("/../a"), "/a")

    def test_trailing(self) -> None:
        """Verify the trailing case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(normalize_path("a/./b/"), "a/b")

    def test_empty(self) -> None:
        """Verify the empty case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(normalize_path(""), ".")

    def test_root(self) -> None:
        """Verify the root case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(normalize_path("/"), "/")


if __name__ == "__main__":
    unittest.main()
