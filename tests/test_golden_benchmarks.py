"""Golden arithmetic checks for the Tests 14 and 16 input data."""

import unittest

from meta_harness.ledger import evaluate
from meta_harness.ledger import ledger_issues


def _calc(label: str, expression: str, stated: float, **extra) -> dict:
    """Build one computation entry.

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
    entry = {"label": label, "expression": expression, "stated": stated}
    entry.update(extra)
    return entry


def _distribution(percents: list[int]) -> dict:
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


def _annual_pair(monthly: float, annual: float) -> list[dict]:
    """Build a monthly and annual savings pair.

    Parameters
    ----------
    monthly : float
        Monthly net savings.
    annual : float
        Annual net savings.

    Returns
    -------
    list of dict
        Monthly and annual entries.
    """
    base = _calc("net savings", "27500 - 400", monthly, period="month")
    extra = {"period": "year", "derived_from": "net savings"}
    top = _calc("annual net", "27100 * 12", annual, **extra)
    return [base, top]


class Test14ArithmeticTests(unittest.TestCase):
    """Verify the Test 14 expected figures."""

    def test_labor_and_savings(self) -> None:
        """The labor and savings figures recompute.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Each expected value is reproduced.
        """
        self.assertAlmostEqual(evaluate("10000 * 8 / 60"), 1333.33, places=2)
        self.assertAlmostEqual(evaluate("10000 * 8 / 60 * 25"), 33333.33, 2)
        self.assertAlmostEqual(evaluate("27500 - 400"), 27100, places=2)
        self.assertAlmostEqual(evaluate("27100 * 12"), 325200, places=2)

    def test_post_automation_labor(self) -> None:
        """The post-automation hours recompute from both channels.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The review and manual hours sum correctly.
        """
        review = evaluate("10000 * 0.20 * 3 / 60")
        manual = evaluate("10000 * 0.10 * 8 / 60")
        self.assertAlmostEqual(review + manual, 233.33, places=2)

    def test_saved_hours(self) -> None:
        """The saved hours equal the difference in labor.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The saved hours are reproduced.
        """
        self.assertAlmostEqual(
            evaluate(
                "10000 * 8 / 60 - (10000 * 0.20 * 3 / 60"
                " + 10000 * 0.10 * 8 / 60)"
            ),
            1100,
            places=2,
        )


class Test16ArithmeticTests(unittest.TestCase):
    """Verify the Test 16 expected figures."""

    def test_routing_counts(self) -> None:
        """The automated, reviewed, and manual counts recompute.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Each count is reproduced.
        """
        self.assertAlmostEqual(evaluate("2000 * 0.60"), 1200, places=2)
        self.assertAlmostEqual(evaluate("2000 * 0.25"), 500, places=2)
        self.assertAlmostEqual(evaluate("2000 * 0.15"), 300, places=2)

    def test_labor_and_savings(self) -> None:
        """The labor and savings figures recompute.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Each expected value is reproduced.
        """
        self.assertAlmostEqual(evaluate("2000 * 6 / 60"), 200, places=2)
        self.assertAlmostEqual(evaluate("2000 * 6 / 60 * 30"), 6000, places=2)
        self.assertAlmostEqual(evaluate("4600 - 500"), 4100, places=2)
        self.assertAlmostEqual(evaluate("4100 * 12"), 49200, places=2)

    def test_post_automation_labor(self) -> None:
        """The post-automation hours recompute from both channels.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The review and manual hours sum correctly.
        """
        review = evaluate("500 * 2 / 60")
        manual = evaluate("300 * 6 / 60")
        self.assertAlmostEqual(review + manual, 46.67, places=2)


class GoldenLedgerTests(unittest.TestCase):
    """Verify the golden totals reconcile through the ledger."""

    def test_test14_annual_pair_reconciles(self) -> None:
        """The annual net savings equals twelve monthly payments.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        entries = _annual_pair(27100, 325200)
        self.assertEqual([], ledger_issues({"computations": entries}))

    def test_test14_distribution_reconciles(self) -> None:
        """The routing split sums to one hundred.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        ledger = {"distributions": [_distribution([70, 20, 10])]}
        self.assertEqual([], ledger_issues(ledger))

    def test_test16_distribution_reconciles(self) -> None:
        """The Test 16 routing split sums to one hundred.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        ledger = {"distributions": [_distribution([60, 25, 15])]}
        self.assertEqual([], ledger_issues(ledger))

    def test_wrong_annual_is_rejected(self) -> None:
        """An annual total that is not twelve months is rejected.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The annual mismatch is reported.
        """
        entries = _annual_pair(27100, 325000)
        self.assertTrue(ledger_issues({"computations": entries}))
