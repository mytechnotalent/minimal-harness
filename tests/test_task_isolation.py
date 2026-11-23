"""Tests for task boundaries and cross-task output isolation."""

import json
import tempfile
import unittest
from pathlib import Path

from meta_harness.agent import Agent
from meta_harness.agent import _prior_requests
from meta_harness.agent import _task_changed
from meta_harness.agent import _workspace_state


def _call(name: str, path: str) -> dict:
    """Build one mutating tool call.

    Parameters
    ----------
    name : str
        Tool name.
    path : str
        Target path.

    Returns
    -------
    dict
        OpenAI-compatible tool call.
    """
    arguments = json.dumps({"path": path})
    return {"function": {"name": name, "arguments": arguments}}


def _history() -> list[dict]:
    """Build a two-task conversation with one edit per task.

    Parameters
    ----------
    None

    Returns
    -------
    list of dict
        Conversation messages.
    """
    old_call = _call("write", "old.txt")
    new_call = _call("write", "new.txt")
    return [
        {"role": "user", "content": "old"},
        {"role": "assistant", "tool_calls": [old_call]},
        {"role": "user", "content": "new"},
        {"role": "assistant", "tool_calls": [new_call]},
    ]


class PriorRequestTests(unittest.TestCase):
    """Verify earlier requests are bounded and separated."""

    def test_only_prior_users_are_kept(self) -> None:
        """Only user messages before the task are returned.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The current request is excluded.
        """
        messages = _history()
        self.assertEqual(["old"], _prior_requests(messages, 2))

    def test_prior_requests_are_capped(self) -> None:
        """At most five earlier requests are returned.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The five newest prior requests remain.
        """
        messages = [
            {"role": "user", "content": f"task {index}"} for index in range(7)
        ]
        self.assertEqual(5, len(_prior_requests(messages, 7)))


class TaskFileTests(unittest.TestCase):
    """Verify only current-task files are reported."""

    def test_prior_edits_are_excluded(self) -> None:
        """Files from an earlier task do not leak in.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only the current task's edit is listed.
        """
        with tempfile.TemporaryDirectory() as folder:
            agent = Agent(Path(folder), client=object())
            agent.messages = _history()
            agent._task_start = 2
            self.assertEqual(["new.txt"], agent._task_files())

    def test_workspace_diff_is_included(self) -> None:
        """New files detected by the workspace diff are listed.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The created file appears in the result.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before = _workspace_state(root)
            (root / "a.txt").write_text("x")
            self.assertIn("a.txt", _task_changed([], root, before))


class ReviewContextTests(unittest.TestCase):
    """Verify the reviewer receives the task boundary."""

    def test_payload_carries_task_context(self) -> None:
        """The payload names the workspace, prior requests, and files.

        Parameters
        ----------
        None

        Returns
        -------
        None
            All three task fields are present.
        """
        with tempfile.TemporaryDirectory() as folder:
            agent = Agent(Path(folder), client=object())
            agent.messages = _history()
            agent._task_start = 2
            payload = agent._review_payload("new", "answer")
        self.assertEqual(["old"], payload["task"]["prior_requests"])
        self.assertEqual(["new.txt"], payload["task"]["changed_files"])

    def test_workspace_is_named(self) -> None:
        """The task context names the active workspace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The resolved workspace path is present.
        """
        with tempfile.TemporaryDirectory() as folder:
            agent = Agent(Path(folder), client=object())
            payload = agent._review_payload("new", "answer")
            workspace = str(Path(folder).resolve())
        self.assertEqual(workspace, payload["task"]["workspace"])
