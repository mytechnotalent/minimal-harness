"""Tests for requirement-state extraction and contradiction checks."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meta_harness.agent import Agent
from meta_harness.requirements import needs_requirements
from meta_harness.requirements import requirement_issues


def _item(
    name: str, state: str, evidence: str = "", used: bool = False
) -> dict:
    """Build one requirement entry.

    Parameters
    ----------
    name : str
        Requirement text.
    state : str
        Requirement state.
    evidence : str
        Supporting detail.
    used : bool
        Whether the answer presents it as confirmed.

    Returns
    -------
    dict
        Requirement entry.
    """
    return {
        "requirement": name,
        "state": state,
        "evidence": evidence,
        "used_as_confirmed": used,
    }


def _ledger(*items: dict) -> dict:
    """Build a requirement ledger.

    Parameters
    ----------
    *items : dict
        Requirement entries.

    Returns
    -------
    dict
        Ledger with the given requirements.
    """
    return {"requirements": list(items)}


def _spec_messages() -> list[dict]:
    """Build a short evolving-specification conversation.

    Parameters
    ----------
    None

    Returns
    -------
    list of dict
        Conversation messages.
    """
    return [
        {"role": "user", "content": "build dashboard"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "confirm permissions"},
    ]


def _spec_agent(folder: str, value: str) -> tuple:
    """Build an agent positioned at an evolving specification.

    Parameters
    ----------
    folder : str
        Temporary workspace.
    value : str
        Extractor response.

    Returns
    -------
    tuple
        Agent and its static client.
    """
    client = StaticClient(value)
    agent = Agent(Path(folder), client=client)
    agent.messages = _spec_messages()
    agent._task_start = 2
    return agent, client


class StaticClient:
    """Return one fixed completion response."""

    def __init__(self, value: str) -> None:
        """Store the response text.

        Parameters
        ----------
        value : str
            Response returned by ``complete``.

        Returns
        -------
        None
            The client is ready.
        """
        self.value = value
        self.calls = 0

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return the stored response.

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
            Stored response text.
        """
        self.calls += 1
        return self.value


class RequirementSelectionTests(unittest.TestCase):
    """Verify when requirement extraction runs."""

    def test_spec_with_history_is_selected(self) -> None:
        """A prior turn plus a spec word triggers extraction.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The prompt is selected.
        """
        self.assertTrue(
            needs_requirements(
                "confirm audit permissions", ["build dashboard"]
            )
        )

    def test_single_task_is_skipped(self) -> None:
        """A first task has no requirement history.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Extraction is skipped.
        """
        self.assertFalse(needs_requirements("build dashboard", []))


class RequirementIssueTests(unittest.TestCase):
    """Verify contradiction and state issues."""

    def test_confirmed_requirement_is_clean(self) -> None:
        """A confirmed requirement yields no issue.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue list is empty.
        """
        ledger = _ledger(_item("read-only access", "confirmed"))
        self.assertEqual([], requirement_issues(ledger))

    def test_contradiction_is_reported(self) -> None:
        """A contradicted requirement is reported with its evidence.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue names the contradiction.
        """
        ledger = _ledger(_item("auth", "contradicted", "prototype vs prod"))
        issue = requirement_issues(ledger)[0]
        self.assertIn("contradicted", issue)
        self.assertIn("prototype vs prod", issue)

    def test_promoted_recommendation_is_reported(self) -> None:
        """A proposed item used as confirmed is reported.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue names the promotion.
        """
        ledger = _ledger(_item("AI logging", "proposed", used=True))
        self.assertIn("presented as confirmed", requirement_issues(ledger)[0])


class RequirementReviewTests(unittest.TestCase):
    """Verify the agent wires extraction into review."""

    def test_review_uses_conversation_history(self) -> None:
        """Requirement findings come from prior requests and the answer.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The promoted recommendation is reported.
        """
        ledger = _ledger(_item("AI logging", "proposed", used=True))
        with tempfile.TemporaryDirectory() as folder:
            agent, _ = _spec_agent(folder, json.dumps(ledger))
            with patch.dict(os.environ, {"HARNESS_REQUIREMENT_CHECK": "on"}):
                result = agent._requirement_review("confirm permissions", "x")
        self.assertIn("presented as confirmed", result["issues"][0])

    def test_payload_includes_requirements(self) -> None:
        """Requirement findings reach the reviewer payload.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The findings are attached unchanged.
        """
        findings = {"issues": ["x"]}
        with tempfile.TemporaryDirectory() as folder:
            agent = Agent(Path(folder), client=object())
            payload = agent._review_payload("q", "a", None, None, findings)
        self.assertEqual(findings, payload["requirements"])
