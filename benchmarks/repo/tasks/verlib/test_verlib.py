"""Hidden tests for the version handling task."""

import unittest

from verlib.version import compare
from verlib.version import parse


class VersionTests(unittest.TestCase):
    """Verify semantic version parsing and ordering."""

    def test_parse_forms(self) -> None:
        """Plain, prerelease, and build forms parse correctly.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(parse("1.2.3"), (1, 2, 3, ()))
        self.assertEqual(parse("1.0.0-alpha.1"), (1, 0, 0, ("alpha", 1)))
        self.assertEqual(parse("1.0.0+build.5"), (1, 0, 0, ()))

    def test_parse_rejects_invalid(self) -> None:
        """Invalid versions raise ValueError.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        for text in ("1.0", "1.0.0-", "v1.0.0", "1.0.0.0"):
            with self.assertRaises(ValueError):
                parse(text)

    def test_compare_ordering(self) -> None:
        """Semver precedence rules are applied.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(compare("1.0.0-alpha", "1.0.0"), -1)
        self.assertEqual(compare("1.0.0-alpha.2", "1.0.0-alpha.10"), -1)
        self.assertEqual(compare("1.0.0-alpha", "1.0.0-alpha.1"), -1)
        self.assertEqual(compare("1.0.1", "1.0.0"), 1)
        self.assertEqual(compare("1.0.0+build.1", "1.0.0+build.2"), 0)


if __name__ == "__main__":
    unittest.main()
