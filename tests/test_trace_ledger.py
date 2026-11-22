"""Tests for the execution ledger and evidence trace."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meta_harness.agent import Agent
from meta_harness.agent import _base_payload


def _traced_agent(folder: str, calls: list) -> Agent:
    """Build an agent and record the given tool calls.

    Parameters
    ----------
    folder : str
        Temporary workspace.
    calls : list
        Tuples of name, arguments, content, and status.

    Returns
    -------
    Agent
        Agent carrying the recorded trace.
    """
    agent = Agent(Path(folder), client=object())
    agent._task_id = "t1"
    for name, arguments, content, status in calls:
        agent._record_trace(name, arguments, content, status)
    return agent


class TraceFieldTests(unittest.TestCase):
    """Verify execution records carry auditable fields."""

    def test_entry_has_ledger_fields(self) -> None:
        """A record names the task, id, and usage flag.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The fields are present and labeled.
        """
        calls = [("read", {"path": "a"}, "ok", "ok")]
        with tempfile.TemporaryDirectory() as folder:
            agent = _traced_agent(folder, calls)
            entry = agent._trace[0]
        self.assertEqual("tool-1", entry["id"])
        self.assertEqual("t1", entry["task"])
        self.assertFalse(entry["used_in_final"])

    def test_failed_attempts_are_preserved(self) -> None:
        """An error record is kept alongside the later success.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both records and their statuses remain.
        """
        calls = [
            ("read", {"path": "a"}, "boom", "error"),
            ("read", {"path": "b"}, "ok", "ok"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            agent = _traced_agent(folder, calls)
        statuses = [entry["status"] for entry in agent._trace]
        self.assertEqual(["error", "ok"], statuses)

    def test_retry_links_identical_calls(self) -> None:
        """A repeated identical call points at its first attempt.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The retry relationship is recorded.
        """
        calls = [
            ("read", {"path": "a"}, "x", "error"),
            ("read", {"path": "a"}, "y", "ok"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            agent = _traced_agent(folder, calls)
        self.assertEqual(agent._trace[0]["id"], agent._trace[1]["retry_of"])

    def test_distinct_calls_are_not_retries(self) -> None:
        """Different arguments do not create a retry link.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The second record has no retry source.
        """
        calls = [
            ("read", {"path": "a"}, "x", "ok"),
            ("read", {"path": "b"}, "y", "ok"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            agent = _traced_agent(folder, calls)
        self.assertIsNone(agent._trace[1]["retry_of"])


class TraceUsageTests(unittest.TestCase):
    """Verify usage marking and trace origin."""

    def test_cited_path_is_marked_used(self) -> None:
        """A path cited in the answer marks the record used.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The usage flag becomes true.
        """
        calls = [("write", {"path": "out.txt"}, "ok", "ok")]
        with tempfile.TemporaryDirectory() as folder:
            agent = _traced_agent(folder, calls)
            agent._mark_trace_usage("Created out.txt for you.")
        self.assertTrue(agent._trace[0]["used_in_final"])

    def test_origin_reflects_available_trace(self) -> None:
        """The payload says whether a live trace exists.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both origin values are reported correctly.
        """
        missing = _base_payload("q", "a", [], [])
        traced = _base_payload("q", "a", [], [{"tool": "read"}])
        self.assertEqual("none", missing["tool_trace_origin"])
        self.assertEqual("recorded", traced["tool_trace_origin"])

    def test_trace_log_is_written(self) -> None:
        """Configured logging appends a JSON line per call.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The logged record names the tool and id.
        """
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "trace.jsonl"
            agent = Agent(Path(folder), client=object())
            with patch.dict(os.environ, {"HARNESS_TRACE_LOG": str(log)}):
                agent._record_trace("read", {"path": "a"}, "ok", "ok")
            rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual("read", rows[0]["tool"])
        self.assertEqual("tool-1", rows[0]["id"])
