"""parse_duration tests."""

import unittest

from solution import parse_duration


class ParseDurationTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_mixed(self) -> None:
        """Verify the mixed case."""
        self.assertEqual(parse_duration("1h30m15s"), 5415000)

    def test_ten_ms(self) -> None:
        """Verify the ten_ms case."""
        self.assertEqual(parse_duration("10ms"), 10)

    def test_minutes_seconds(self) -> None:
        """Verify the minutes_seconds case."""
        self.assertEqual(parse_duration("2m3s"), 123000)

    def test_whitespace(self) -> None:
        """Verify the whitespace case."""
        self.assertEqual(parse_duration(" 1h "), 3600000)

    def test_empty(self) -> None:
        """Verify the empty case."""
        with self.assertRaises(ValueError):
            parse_duration("")


if __name__ == "__main__":
    unittest.main()
