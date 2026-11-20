"""Tests for reviewer calibration."""

import tempfile
import unittest
from pathlib import Path

from scripts.calibrate_reviewer import load_records
from scripts.calibrate_reviewer import summarize

_RECORDS = (
    {"review": True, "truth": True},
    {"review": True, "truth": False},
    {"review": False, "truth": True},
    {"review": False, "truth": False},
)


class CalibrationTests(unittest.TestCase):
    """Verify confusion counts and rates."""

    def test_summary_counts_and_rates(self) -> None:
        """A balanced sample yields expected counts and rates.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Counts and rates match the sample.
        """
        summary = summarize(list(_RECORDS))
        self.assertEqual(summary["tp"], 1)
        self.assertEqual(summary["fp"], 1)
        self.assertEqual(summary["precision"], 0.5)
        self.assertEqual(summary["recall"], 0.5)

    def test_empty_summary_is_zero(self) -> None:
        """An empty sample reports zero rates.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Rates are zero and no division fails.
        """
        summary = summarize([])
        self.assertEqual(summary["precision"], 0.0)
        self.assertEqual(summary["accuracy"], 0.0)

    def test_load_records_skips_blank_lines(self) -> None:
        """Blank JSONL lines are ignored.

        Parameters
        ----------
        None

        Returns
        -------
        None
            One record is loaded.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "records.jsonl")
            path.write_text('{"review": true, "truth": false}\n\n')
            records = load_records(path)
        self.assertTrue(records[0]["review"])
        self.assertFalse(records[0]["truth"])
