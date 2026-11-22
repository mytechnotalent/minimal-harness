"""Tests for the benchmark regression entry loader and checks."""

import tempfile
import unittest
from pathlib import Path

from meta_harness.regression import check_score
from meta_harness.regression import evaluate_checks
from meta_harness.regression import passed
from meta_harness.regression import prompt_hash
from meta_harness.regression import validate_entry


def _entry() -> dict:
    """Build a synthetic, non-benchmark entry.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Entry used only to exercise the schema.
    """
    entry = {"id": "example", "purpose": "Exercise the schema"}
    entry["prompt_version"] = "example"
    entry["sequence"] = ["Say hello"]
    entry["config"] = {"model": "test", "max_turns": 1}
    entry["checks"] = [{"type": "contains", "value": "hello"}]
    entry["rubric"] = {"pass_threshold": 1.0}
    return entry


class EntryValidationTests(unittest.TestCase):
    """Verify required fields and check shapes."""

    def test_valid_entry_passes(self) -> None:
        """A complete entry validates.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No errors are returned.
        """
        self.assertEqual([], validate_entry(_entry()))

    def test_missing_field_is_reported(self) -> None:
        """A missing required field is reported.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The error list is non-empty.
        """
        entry = _entry()
        entry.pop("purpose")
        self.assertTrue(validate_entry(entry))

    def test_unknown_check_type_is_reported(self) -> None:
        """An unknown check type is reported.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The error list is non-empty.
        """
        entry = _entry()
        entry["checks"] = [{"type": "nope"}]
        self.assertTrue(validate_entry(entry))

    def test_status_check_requires_values(self) -> None:
        """A status check without values is rejected.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The error list is non-empty.
        """
        entry = _entry()
        entry["checks"] = [{"type": "status_in"}]
        self.assertTrue(validate_entry(entry))


class PromptHashTests(unittest.TestCase):
    """Verify the prompt fingerprint is stable."""

    def test_hash_is_stable(self) -> None:
        """The same sequence produces the same digest.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both digests are equal.
        """
        sequence = ["first", "second"]
        self.assertEqual(prompt_hash(sequence), prompt_hash(sequence))

    def test_hash_changes_with_prompt(self) -> None:
        """Changing a prompt changes the digest.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The digests differ.
        """
        self.assertNotEqual(prompt_hash(["a"]), prompt_hash(["b"]))


class CheckTests(unittest.TestCase):
    """Verify each deterministic check type."""

    def test_contains_check(self) -> None:
        """A present phrase passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The check passes.
        """
        checks = [{"type": "contains", "value": "hi"}]
        self.assertTrue(evaluate_checks(checks, "hi there", ".")[0]["passed"])

    def test_not_contains_check(self) -> None:
        """An absent phrase passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The check passes.
        """
        checks = [{"type": "not_contains", "value": "sql"}]
        self.assertTrue(evaluate_checks(checks, "csv only", ".")[0]["passed"])

    def test_regex_check(self) -> None:
        """A matching expression passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The check passes.
        """
        checks = [{"type": "regex", "value": r"\bCSV\b"}]
        self.assertTrue(evaluate_checks(checks, "CSV audit", ".")[0]["passed"])

    def test_file_exists_check(self) -> None:
        """An existing file passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The check passes.
        """
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "out.txt").write_text("x")
            checks = [{"type": "file_exists", "value": "out.txt"}]
            results = evaluate_checks(checks, "", folder)
        self.assertTrue(results[0]["passed"])

    def test_status_check(self) -> None:
        """An allowed status passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The check passes.
        """
        checks = [{"type": "status_in", "values": ["verified"]}]
        answer = "Status: verified."
        self.assertTrue(evaluate_checks(checks, answer, ".")[0]["passed"])


class ScoringTests(unittest.TestCase):
    """Verify score aggregation and thresholds."""

    def test_score_is_fraction(self) -> None:
        """The score is the passed fraction.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The fraction is returned.
        """
        results = [{"passed": True}, {"passed": False}]
        self.assertEqual(0.5, check_score(results))

    def test_threshold_rejects_low_score(self) -> None:
        """A score below the threshold fails.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The run is not passed.
        """
        results = [{"passed": True}, {"passed": False}]
        self.assertFalse(passed(results, 0.75))
