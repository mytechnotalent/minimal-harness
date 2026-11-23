"""Tests for answer limits, constraint status, and tool provenance."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meta_harness.agent import Agent
from meta_harness.agent import _base_payload
from meta_harness.agent import _invariant_mode
from meta_harness.agent import _ledger_mode
from meta_harness.agent import _redact_arguments
from meta_harness.agent import _verification_issues
from meta_harness.invariants import needs_invariants
from meta_harness.ledger import ledger_issues
from meta_harness.ledger import limit_issues
from meta_harness.ledger import needs_ledger


class LimitClient:
    """Return a fixed ledger response."""

    def __init__(self, value: str) -> None:
        """Store the response text.

        Parameters
        ----------
        value : str
            Raw ledger JSON.

        Returns
        -------
        None
            The client is ready.
        """
        self.value = value

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return the stored ledger text.

        Parameters
        ----------
        system : str
            System instruction.
        user : str
            User payload.
        temperature : float
            Sampling temperature.

        Returns
        -------
        str
            Raw ledger text.
        """
        return self.value


def _impossible_ledger() -> dict:
    """Build a ledger with one impossible constraint.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Ledger with an impossible constraint.
    """
    entry = {
        "requirement": "under 50 g carbs",
        "status": "impossible",
        "evidence": "needs at least 60 g",
    }
    return {"constraints": [entry]}


class AnswerLimitTests(unittest.TestCase):
    """Verify word and character limit checks."""

    def test_word_overrun_is_reported(self) -> None:
        """An answer over the word limit becomes an issue.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue names the count and the limit.
        """
        issues = limit_issues("Summarize in 5 words", "one two three four 5 6")
        self.assertIn("6 words", issues[0])
        self.assertIn("limit is 5", issues[0])

    def test_word_limit_can_pass(self) -> None:
        """An answer within the word limit is clean.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        self.assertEqual([], limit_issues("Answer in at most 10 words", "a b"))

    def test_character_overrun_is_reported(self) -> None:
        """An answer over the character limit becomes an issue.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue names the character count.
        """
        issues = limit_issues("Use no more than 5 characters", "abcdef")
        self.assertIn("6 characters", issues[0])

    def test_overlapping_phrases_are_deduped(self) -> None:
        """Overlapping limit phrases yield one issue.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only one issue is returned.
        """
        issues = limit_issues("Write it in 2 words or fewer", "a b c")
        self.assertEqual(1, len(issues))

    def test_limit_alone_requests_ledger(self) -> None:
        """A limit-only prompt still enables verification.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The limit prompt is selected without other numeric words.
        """
        self.assertTrue(needs_ledger("Answer in 5 words", ""))

    def test_impossible_constraint_is_reported(self) -> None:
        """An impossible constraint becomes an issue with its reason.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The requirement and reason are named.
        """
        issue = ledger_issues(_impossible_ledger())[0]
        self.assertIn("impossible", issue)
        self.assertIn("needs at least 60 g", issue)

    def test_limits_and_ledger_are_combined(self) -> None:
        """Limit issues and arithmetic issues are merged.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both issue kinds are present.
        """
        ledger = {
            "computations": [
                {"label": "total", "expression": "1 + 1", "stated": 3}
            ]
        }
        issues = _verification_issues("Answer in 1 word", "a b c", ledger)
        self.assertEqual(2, len(issues))

    def test_ledger_runs_for_limit_only_prompt(self) -> None:
        """A limit-only prompt returns deterministic issues.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The ledger result carries the word overrun.
        """
        with tempfile.TemporaryDirectory() as folder:
            agent = Agent(Path(folder), client=LimitClient("{}"))
            with patch.dict(os.environ, {"HARNESS_ANSWER_LEDGER": "on"}):
                result = agent._verify_ledger("in 2 words", "a b c")
        self.assertIn("3 words", result["issues"][0])


class DefaultVerificationTests(unittest.TestCase):
    """Verify that verification is on by default."""

    def test_default_modes_are_auto(self) -> None:
        """Ledger and invariant checks default to auto.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both modes resolve to auto with no environment set.
        """
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual("auto", _ledger_mode())
            self.assertEqual("auto", _invariant_mode())

    def test_review_defaults_on(self) -> None:
        """A capable client reviews by default.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Review is enabled without an environment override.
        """
        with tempfile.TemporaryDirectory() as folder:
            agent = Agent(Path(folder), client=LimitClient("{}"))
            with patch.dict(os.environ, {}, clear=True):
                self.assertTrue(agent._review_enabled("def f(): pass"))

    def test_combined_task_triggers_both_checks(self) -> None:
        """Arithmetic and retry tasks select both checks.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The ledger and invariant triggers both fire.
        """
        prompt = "Fix the invoice total and the duplicate retries."
        self.assertTrue(needs_ledger(prompt, "the total is 10"))
        self.assertTrue(needs_invariants(prompt, "retry with request id"))


class ToolTraceTests(unittest.TestCase):
    """Verify auditable tool provenance records."""

    def test_secret_arguments_are_redacted(self) -> None:
        """Secret-named arguments are masked.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The token is replaced and the path kept.
        """
        result = _redact_arguments({"token": "abc", "path": "x"})
        self.assertEqual("[redacted]", result["token"])
        self.assertEqual("x", result["path"])

    def test_long_arguments_are_shortened(self) -> None:
        """Long string arguments are capped.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The value length is bounded.
        """
        result = _redact_arguments({"text": "a" * 300})
        self.assertEqual(200, len(result["text"]))

    def test_trace_records_a_call(self) -> None:
        """A recorded call carries tool, time, and status.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The trace entry is present and labeled.
        """
        with tempfile.TemporaryDirectory() as folder:
            agent = Agent(Path(folder), client=object())
            agent._record_trace("read", {"path": "a"}, "ok", "ok")
            entry = agent._trace[0]
        self.assertEqual("read", entry["tool"])
        self.assertEqual("ok", entry["status"])
        self.assertIn("at", entry)

    def test_run_resets_the_trace(self) -> None:
        """A new run starts with an empty trace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The trace is cleared before the new task.
        """
        with tempfile.TemporaryDirectory() as folder:
            agent = Agent(Path(folder), client=object(), max_turns=1)
            agent._record_trace("read", {}, "ok", "ok")
            agent._begin_run("new task")
            self.assertEqual([], agent._trace)

    def test_payload_includes_the_trace(self) -> None:
        """The reviewer payload carries the trace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The supplied trace is attached unchanged.
        """
        trace = [{"tool": "read", "status": "ok"}]
        payload = _base_payload("q", "a", [], trace)
        self.assertEqual(trace, payload["tool_trace"])

    def test_review_payload_includes_the_trace(self) -> None:
        """The agent attaches its live trace to the review payload.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The recorded tool appears in the payload.
        """
        with tempfile.TemporaryDirectory() as folder:
            agent = Agent(Path(folder), client=object(), max_turns=1)
            agent._record_trace("read", {}, "ok", "ok")
            payload = agent._review_payload("q", "a")
        self.assertEqual("read", payload["tool_trace"][0]["tool"])
