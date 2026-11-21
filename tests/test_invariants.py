"""Tests for curated technical invariant selection."""

import unittest

from meta_harness.invariants import needs_invariants
from meta_harness.invariants import relevant_invariants


class InvariantSelectionTests(unittest.TestCase):
    """Verify keyword-based invariant selection."""

    def test_database_invariants_are_selected(self) -> None:
        """PostgreSQL questions get the database checklist.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The UNIQUE constraint rule is present.
        """
        rules = relevant_invariants("postgres unique constraint", "draft")
        self.assertTrue(any("UNIQUE constraint" in rule for rule in rules))

    def test_retry_invariants_are_selected(self) -> None:
        """Retry questions get the idempotency checklist.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The request ID rule is present.
        """
        rules = relevant_invariants("request id and idempotency key", "draft")
        self.assertTrue(any("request ID" in rule for rule in rules))

    def test_news_has_no_invariants(self) -> None:
        """A news request does not trigger a technical checklist.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No rules are selected.
        """
        self.assertEqual(relevant_invariants("find news stories", "draft"), [])
        self.assertFalse(needs_invariants("find news stories", "draft"))
