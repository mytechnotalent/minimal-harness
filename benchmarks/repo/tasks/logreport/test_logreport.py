"""Hidden tests for the log report task."""

import unittest

from logs.parser import parse_line
from logs.report import filter_level
from logs.report import summarize

LINES = [
    "2024-01-02T03:04:05 INFO started",
    "2024-01-02T03:04:06 WARN disk low",
    "garbage",
    "2024-01-02T03:04:07 ERROR failed hard",
    "2024-01-02T03:04:08 INFO done",
]


class LogReportTests(unittest.TestCase):
    """Verify parsing and reporting."""

    def test_parse_line(self) -> None:
        """Valid lines parse and invalid lines return None.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        parsed = parse_line(LINES[0])
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["message"], "started")
        self.assertEqual(parsed["time"], "2024-01-02T03:04:05")
        self.assertIsNone(parse_line("2024-01-02T03:04:05 TRACE nope"))
        self.assertIsNone(parse_line("not a log line"))

    def test_summarize(self) -> None:
        """Summary counts levels and invalid lines.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        summary = summarize(LINES)
        self.assertEqual(summary["counts"], {"INFO": 2, "WARN": 1, "ERROR": 1})
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(summary["first"], "2024-01-02T03:04:05")
        self.assertEqual(summary["last"], "2024-01-02T03:04:08")

    def test_filter_level(self) -> None:
        """Filtering keeps messages in order.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(filter_level(LINES, "INFO"), ["started", "done"])
        self.assertEqual(filter_level(LINES, "WARN"), ["disk low"])


if __name__ == "__main__":
    unittest.main()
