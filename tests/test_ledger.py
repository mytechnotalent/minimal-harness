"""Tests for deterministic ledger checks."""

import unittest

from meta_harness.ledger import evaluate
from meta_harness.ledger import ledger_issues
from meta_harness.ledger import needs_ledger


def _computation(stated: float) -> dict:
    """Build one computation entry.

    Parameters
    ----------
    stated : float
        Number claimed by the answer.

    Returns
    -------
    dict
        Computation entry.
    """
    return {
        "label": "day 1 protein",
        "expression": "12 + 22 + 13.5",
        "stated": stated,
    }


class LedgerMathTests(unittest.TestCase):
    """Verify safe arithmetic evaluation."""

    def test_arithmetic_is_evaluated(self) -> None:
        """Basic operators and parentheses work.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The result matches the expression.
        """
        self.assertEqual(evaluate("12 + 22 + 13.5"), 47.5)
        self.assertEqual(evaluate("(2 + 3) * 4"), 20.0)

    def test_calls_are_rejected(self) -> None:
        """Function calls are rejected instead of executed.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ``ValueError`` is raised.
        """
        with self.assertRaises(ValueError):
            evaluate("__import__('os').system('true')")

    def test_mismatch_is_reported(self) -> None:
        """A stated total that does not recompute is flagged.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue names the recomputed value.
        """
        ledger = {"computations": [_computation(75)]}
        issues = ledger_issues(ledger)
        self.assertEqual(len(issues), 1)
        self.assertIn("recomputed 47.5", issues[0])

    def test_matching_total_is_clean(self) -> None:
        """A total within tolerance passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        ledger = {"computations": [_computation(47.5)]}
        self.assertEqual(ledger_issues(ledger), [])

    def test_partial_constraint_is_reported(self) -> None:
        """A partial constraint becomes an issue.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue names the requirement.
        """
        ledger = {
            "constraints": [
                {"requirement": "100 g protein", "status": "partial"}
            ]
        }
        self.assertIn("100 g protein", ledger_issues(ledger)[0])

    def test_meal_plan_needs_a_ledger(self) -> None:
        """Numeric constraint tasks are selected for checking.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only the numeric prompt triggers a ledger.
        """
        self.assertTrue(
            needs_ledger("meal plan with 100 g protein and a $65 budget", "")
        )
        self.assertFalse(needs_ledger("find recent news stories", "draft"))
