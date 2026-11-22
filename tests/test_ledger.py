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


def _entry(**overrides) -> dict:
    """Build one computation entry with optional overrides.

    Parameters
    ----------
    **overrides
        Fields replacing the defaults.

    Returns
    -------
    dict
        Computation entry.
    """
    entry = {"label": "total", "expression": "10 + 10", "stated": 20}
    entry.update(overrides)
    return entry


def _routing(percents: list[int]) -> dict:
    """Build a routing distribution entry.

    Parameters
    ----------
    percents : list of int
        Percentage parts.

    Returns
    -------
    dict
        Distribution entry.
    """
    parts = [
        {"name": str(index), "percent": value}
        for index, value in enumerate(percents)
    ]
    return {"label": "routing", "parts": parts}


def _period_entries(annual: float) -> list[dict]:
    """Build a monthly and annual pair.

    Parameters
    ----------
    annual : float
        Annual total to check.

    Returns
    -------
    list of dict
        Monthly and annual computation entries.
    """
    return [_monthly_entry(), _annual_entry(annual)]


def _monthly_entry() -> dict:
    """Build the monthly net savings entry.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Monthly computation entry.
    """
    return _savings_entry("net savings", "27500 - 400", 27100, period="month")


def _annual_entry(annual: float) -> dict:
    """Build the annual net savings entry.

    Parameters
    ----------
    annual : float
        Annual total.

    Returns
    -------
    dict
        Annual computation entry.
    """
    return _savings_entry(
        "annual net savings",
        "27100 * 12",
        annual,
        period="year",
        derived_from="net savings",
    )


def _savings_entry(
    label: str, expression: str, stated: float, **extra
) -> dict:
    """Build one savings computation entry.

    Parameters
    ----------
    label : str
        Entry label.
    expression : str
        Arithmetic expression.
    stated : float
        Number claimed by the answer.
    **extra
        Additional entry fields.

    Returns
    -------
    dict
        Computation entry.
    """
    return _entry(label=label, expression=expression, stated=stated, **extra)


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

    def test_derived_without_expression_is_flagged(self) -> None:
        """A derived total with no arithmetic is flagged.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue says the number cannot be verified.
        """
        entry = _entry(expression="", stated=9693.33, derived=True)
        ledger = {"computations": [entry]}
        self.assertIn("no arithmetic", ledger_issues(ledger)[0])

    def test_plain_number_is_not_flagged(self) -> None:
        """A non-derived number needs no arithmetic.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        ledger = {"computations": [_entry(expression="", stated=3)]}
        self.assertEqual([], ledger_issues(ledger))

    def test_stated_tolerance_is_used(self) -> None:
        """A rounding tolerance from the answer prevents a false mismatch.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        entry = _entry(expression="100 / 3", stated=33.3, tolerance=0.05)
        self.assertEqual([], ledger_issues({"computations": [entry]}))

    def test_tight_tolerance_flags_mismatch(self) -> None:
        """A tolerance too small to cover the rounding is rejected.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The recomputed value is reported.
        """
        entry = _entry(expression="100 / 3", stated=33.3, tolerance=0.01)
        ledger = {"computations": [entry]}
        self.assertIn("recomputed", ledger_issues(ledger)[0])

    def test_sensitivity_scenario_is_recomputed(self) -> None:
        """A scenario total is recomputed from its own expression.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The correct scenario value is reported.
        """
        entry = _entry(
            label="conservative savings",
            expression="30 * 8 * 40",
            stated=10000,
        )
        ledger = {"computations": [entry]}
        self.assertIn("recomputed 9600", ledger_issues(ledger)[0])

    def test_small_financial_error_is_flagged(self) -> None:
        """A small percentage error is not hidden by a loose tolerance.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The recomputed value is reported.
        """
        entry = _entry(
            label="gross savings",
            expression="9706.67",
            stated=9693.33,
        )
        ledger = {"computations": [entry]}
        self.assertIn("recomputed", ledger_issues(ledger)[0])

    def test_distribution_sums_to_100(self) -> None:
        """A distribution totaling 100 passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        ledger = {"distributions": [_routing([70, 20, 10])]}
        self.assertEqual([], ledger_issues(ledger))

    def test_distribution_over_100_is_reported(self) -> None:
        """A distribution above 100 is flagged.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The distribution label is reported.
        """
        ledger = {"distributions": [_routing([70, 40])]}
        self.assertIn("routing", ledger_issues(ledger)[0])

    def test_annual_total_reconciles(self) -> None:
        """An annual total equal to twelve months passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        entries = _period_entries(325200)
        self.assertEqual([], ledger_issues({"computations": entries}))

    def test_annual_total_mismatch_is_reported(self) -> None:
        """An annual total that is not twelve months is flagged.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The annual label is reported.
        """
        entries = _period_entries(325000)
        issue = ledger_issues({"computations": entries})[0]
        self.assertIn("annual net savings", issue)

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
