"""Tests for the campaign confidence summary."""

import unittest

from scripts.campaign import summarize
from scripts.campaign import wilson

_REPORT = {
    "tasks": [
        {"harness_runs": [1.0, 1.0], "pi_runs": [1.0, 0.0]},
        {"harness_runs": [0.0, 1.0], "pi_runs": [0.0, 0.0]},
    ]
}


class CampaignTests(unittest.TestCase):
    """Verify rates, deltas, and interval bounds."""

    def test_summarize_rates_and_delta(self) -> None:
        """The summary averages runs and pairs tasks.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Rates and the paired delta match the sample.
        """
        summary = summarize(_REPORT)
        self.assertEqual(summary["harness_rate"], 0.75)
        self.assertEqual(summary["baseline_rate"], 0.25)
        self.assertEqual(summary["delta"], 0.5)

    def test_wilson_interval_is_bounded(self) -> None:
        """The Wilson interval stays within zero and one.

        Parameters
        ----------
        None

        Returns
        -------
        None
            A perfect sample has a high lower bound.
        """
        low, high = wilson(10, 10)
        self.assertGreater(low, 0.7)
        self.assertLessEqual(high, 1.0)

    def test_empty_wilson_is_zero(self) -> None:
        """An empty sample returns a zero interval.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both bounds are zero.
        """
        self.assertEqual(wilson(0, 0), (0.0, 0.0))
