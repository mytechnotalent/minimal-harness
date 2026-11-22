"""Tests for the shipped golden regression entries."""

import unittest
from pathlib import Path

from meta_harness.regression import load_entry
from meta_harness.regression import validate_entry

_ENTRY_DIR = Path("benchmarks/regression/tests")


def _entry(name: str) -> dict:
    """Load one shipped entry.

    Parameters
    ----------
    name : str
        Entry file name without suffix.

    Returns
    -------
    dict
        Parsed entry.
    """
    return load_entry(_ENTRY_DIR / f"{name}.json")


class ShippedEntryTests(unittest.TestCase):
    """Verify the golden entries are valid and labeled honestly."""

    def test_entries_validate(self) -> None:
        """Both shipped entries pass validation.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No validation errors are returned.
        """
        self.assertEqual([], validate_entry(_entry("14")))
        self.assertEqual([], validate_entry(_entry("16")))

    def test_prompts_are_not_mislabeled(self) -> None:
        """Reconstructed prompts are not labeled as originals.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The prompt version names the reconstruction.
        """
        for name in ("14", "16"):
            self.assertEqual(
                "reconstructed-from-listed-inputs",
                _entry(name)["prompt_version"],
            )

    def test_test14_keeps_historical_score(self) -> None:
        """The historical score is preserved separately.

        Parameters
        ----------
        None

        Returns
        -------
        None
            History records the evaluator score and source.
        """
        history = _entry("14")["history"][0]
        self.assertEqual(100, history["score"])
        self.assertIn("Phase 2", history["source"])

    def test_test14_has_annual_and_capacity_checks(self) -> None:
        """The golden checks cover the annual figure and capacity claim.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The key checks are present.
        """
        values = [check.get("value") for check in _entry("14")["checks"]]
        self.assertTrue(any("325,?200" in value for value in values))
        self.assertTrue(any("capacity" in value for value in values))

    def test_test16_has_retry_check(self) -> None:
        """The golden checks cover duplicate prevention.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The retry safeguard check is present.
        """
        values = [check.get("value") for check in _entry("16")["checks"]]
        self.assertTrue(any("idempoten" in value for value in values))
