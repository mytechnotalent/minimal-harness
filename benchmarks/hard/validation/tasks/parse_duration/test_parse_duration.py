"""parse_duration tests."""

import unittest

from solution import parse_duration


class ParseDurationTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_zero(self) -> None:
        """Verify the zero case."""
        self.assertEqual(parse_duration("0s"), 0)

    def test_milliseconds(self) -> None:
        """Verify the milliseconds case."""
        self.assertEqual(parse_duration("500ms"), 500)

    def test_zero_minutes(self) -> None:
        """Verify the zero_minutes case."""
        self.assertEqual(parse_duration("1h0m"), 3600000)

    def test_minutes_only(self) -> None:
        """Verify the minutes_only case."""
        self.assertEqual(parse_duration("90m"), 5400000)

    def test_invalid(self) -> None:
        """Verify the invalid case."""
        with self.assertRaises(ValueError):
            parse_duration("1x")


if __name__ == "__main__":
    unittest.main()
