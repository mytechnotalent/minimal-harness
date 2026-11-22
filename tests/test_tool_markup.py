"""Tests for recovering tool-call markup emitted as plain text."""

import tempfile
import unittest
from pathlib import Path

from meta_harness.agent import Agent
from meta_harness.agent import _markup_calls
from meta_harness.agent import _recover_markup_calls
from meta_harness.agent import _strip_markup

_MARKUP = (
    "<tool_calls:x><tool_call:x>{name}"
    "<arg_key:x>path</arg_key:x>"
    "<arg_value:x>out.txt</arg_value:x>"
    "<arg_key:x>content</arg_key:x>"
    "<arg_value:x>{content}</arg_value:x>"
    "</tool_call:x></tool_calls:x>"
)


class ScriptedClient:
    """Return scripted assistant replies in order."""

    def __init__(self, replies: list[str]) -> None:
        """Store the reply queue.

        Parameters
        ----------
        replies : list of str
            Assistant contents to return.

        Returns
        -------
        None
            The queue is ready.
        """
        self.replies = list(replies)

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return the next scripted reply.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages.
        tools : list[dict]
            Advertised tool schemas.

        Returns
        -------
        dict
            Chat-completion response.
        """
        content = self.replies.pop(0)
        return {"choices": [{"message": {"content": content}}]}


class MarkupParseTests(unittest.TestCase):
    """Verify parsing and stripping of embedded markup."""

    def test_calls_are_parsed(self) -> None:
        """Markup becomes one call with parsed arguments.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The tool name and arguments are recovered.
        """
        calls = _markup_calls(_MARKUP.format(name="write", content="hi"))
        self.assertEqual("write", calls[0]["function"]["name"])
        self.assertIn('"hi"', calls[0]["function"]["arguments"])

    def test_markup_is_stripped(self) -> None:
        """A markup block is removed from surrounding text.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only the human text remains.
        """
        raw = "note " + _MARKUP.format(name="write", content="hi")
        self.assertEqual("note", _strip_markup(raw))

    def test_unknown_tool_is_not_recovered(self) -> None:
        """Markup naming an unknown tool stays plain text.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No tool calls are set.
        """
        message = {
            "role": "assistant",
            "content": _MARKUP.format(name="frobnicate", content="x"),
        }
        _recover_markup_calls(message, {"write"})
        self.assertFalse(message.get("tool_calls"))

    def test_known_tool_is_recovered(self) -> None:
        """Markup naming a known tool becomes a real call.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The call is set and the content cleared.
        """
        message = {
            "role": "assistant",
            "content": _MARKUP.format(name="write", content="hi"),
        }
        _recover_markup_calls(message, {"write"})
        self.assertEqual("write", message["tool_calls"][0]["function"]["name"])
        self.assertEqual("", message["content"])


class MarkupAgentTests(unittest.TestCase):
    """Verify the agent executes recovered calls."""

    def test_markup_call_runs_in_loop(self) -> None:
        """A recovered call executes before the next reply.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The file exists and the final answer is returned.
        """
        replies = [_MARKUP.format(name="write", content="hi"), "done"]
        with tempfile.TemporaryDirectory() as folder:
            client = ScriptedClient(replies)
            agent = Agent(Path(folder), client=client, max_turns=2)
            result = agent.run("make a file")
            written = (Path(folder) / "out.txt").read_text()
        self.assertEqual("done", result)
        self.assertEqual("hi", written)

    def test_turn_limit_names_the_budget(self) -> None:
        """The fallback states the configured turn count.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The message names the limit instead of staying generic.
        """
        replies = [_MARKUP.format(name="write", content="hi")] * 3
        with tempfile.TemporaryDirectory() as folder:
            client = ScriptedClient(replies)
            agent = Agent(Path(folder), client=client, max_turns=1)
            result = agent.run("make a file")
        self.assertIn("limit of 1 turns", result)

    def test_markup_call_runs_after_turn_limit(self) -> None:
        """A recovered call is not returned raw at the turn limit.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The final reply is clean text.
        """
        replies = [_MARKUP.format(name="write", content="hi"), "final"]
        with tempfile.TemporaryDirectory() as folder:
            client = ScriptedClient(replies)
            agent = Agent(Path(folder), client=client, max_turns=1)
            result = agent.run("make a file")
        self.assertEqual("final", result)
