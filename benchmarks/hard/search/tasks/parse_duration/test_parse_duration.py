"""parse_duration tests."""

import unittest

from solution import parse_duration


class ParseDurationTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_basic(self) -> None:
        """Verify the basic case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(parse_duration("1h30m"), 5400000)

    def test_seconds(self) -> None:
        """Verify the seconds case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(parse_duration("45s"), 45000)

    def test_hours(self) -> None:
        """Verify the hours case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(parse_duration("2h"), 7200000)


if __name__ == "__main__":
    unittest.main()
