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

    def test_privilege_invariants_are_selected(self) -> None:
        """Privilege questions get inherited-access rules.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The inherited privilege rule is present.
        """
        rules = relevant_invariants("grant inherited role privileges", "")
        self.assertTrue(any("inherited" in rule for rule in rules))

    def test_recovery_invariants_are_selected(self) -> None:
        """Recovery questions get the partial-failure rule.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The recovery rule is present.
        """
        rules = relevant_invariants("recovery after partial failure", "")
        self.assertTrue(any("Recovery behavior" in rule for rule in rules))

    def test_idempotency_lifecycle_is_selected(self) -> None:
        """An idempotency question gets the lifecycle rules.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The payload fingerprint and stored result rules are present.
        """
        rules = relevant_invariants("concurrent idempotency key", "")
        self.assertTrue(any("payload fingerprint" in rule for rule in rules))
        self.assertTrue(any("stored result" in rule for rule in rules))

    def test_replay_is_selected(self) -> None:
        """A duplicate payment question gets the replay rule.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The stored-result rule is present.
        """
        rules = relevant_invariants("duplicate payment replay", "")
        self.assertTrue(any("stored result" in rule for rule in rules))

    def test_architecture_outbox_is_selected(self) -> None:
        """An audit-event design gets the outbox rule.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The transaction boundary rule is present.
        """
        rules = relevant_invariants("architecture audit event outbox", "")
        self.assertTrue(any("transactional outbox" in rule for rule in rules))

    def test_architecture_worker_is_selected(self) -> None:
        """A document-processing design gets the worker authz rule.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The worker authorization rule is present.
        """
        rules = relevant_invariants("document processing worker", "")
        self.assertTrue(any("worker must verify" in rule for rule in rules))

    def test_architecture_cost_is_selected(self) -> None:
        """A cost-estimate design gets the cost rules.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The per-unit cost rule is present.
        """
        rules = relevant_invariants("cost estimate per page", "")
        self.assertTrue(any("cost per unit" in rule for rule in rules))

    def test_unstable_key_is_selected(self) -> None:
        """A new-key-per-retry question gets the stability rule.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The key stability rule is present.
        """
        rules = relevant_invariants("new idempotency key per retry", "")
        self.assertTrue(
            any("new key for every retry" in rule for rule in rules)
        )

    def test_upsert_rule_is_selected(self) -> None:
        """An upsert question gets the constraint rule.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The upsert uniqueness rule is present.
        """
        rules = relevant_invariants("upsert unique constraint", "")
        self.assertTrue(any("upsert" in rule for rule in rules))

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
