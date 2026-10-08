"""Tests for the Pi-like interactive tool runtime."""

import json
import tempfile
import unittest
from pathlib import Path

from meta_harness.agent import Agent
from meta_harness.tools import ToolError, ToolRegistry


class AgentTests(unittest.TestCase):
    """Verify model-driven tool execution and workspace safety."""

    def test_agent_executes_write_then_returns_final_text(self) -> None:
        """Execute a model-requested write before final response.

        Returns
        -------
        None
            Assertions pass when the tool loop completes.
        """
        client = ToolCallClient()
        with tempfile.TemporaryDirectory() as directory:
            answer = Agent(directory, client=client).run("Build an app")
            content = Path(directory, "index.html").read_text()
        self.assertEqual(answer, "App created")
        self.assertEqual(content, "<h1>Minimal Harness</h1>")
        self.assertEqual(client.calls, 2)

    def test_registry_rejects_path_escape(self) -> None:
        """Reject file operations outside the workspace root.

        Returns
        -------
        None
            Assertions pass when traversal is blocked.
        """
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ToolError):
                ToolRegistry(directory).write("../escape.txt", "bad")

    def test_agent_starts_with_ask_prompt(self) -> None:
        """The agent begins with the ask-don't-assume system prompt.

        Returns
        -------
        None
            Assertions pass when the system message is present.
        """
        agent = Agent(".", client=ToolCallClient())
        self.assertEqual(agent.messages[0]["role"], "system")
        self.assertIn("ask", agent.messages[0]["content"].lower())

    def test_ask_tool_uses_questioner(self) -> None:
        """The ask tool returns the questioner's chosen answer.

        Returns
        -------
        None
            Assertions pass when the answer is returned.
        """
        registry = ToolRegistry(".", questioner=lambda q, opts: "beta")
        raw = registry.execute(
            "ask", {"question": "Pick", "options": ["alpha", "beta"]}
        )
        self.assertEqual(json.loads(raw)["answer"], "beta")

    def test_ask_tool_hidden_without_questioner(self) -> None:
        """The ask tool is only advertised with a questioner wired.

        Returns
        -------
        None
            Assertions pass when visibility tracks the questioner.
        """
        bare = ToolRegistry(".")
        self.assertNotIn("ask", self._names(bare))
        self.assertNotIn("suggest", self._names(bare))
        wired = ToolRegistry(".", questioner=lambda q, opts: "x")
        self.assertIn("ask", self._names(wired))
        self.assertIn("suggest", self._names(wired))

    def test_suggest_tool_records_short_options(self) -> None:
        """The suggest tool stores short clickable labels.

        Returns
        -------
        None
            Assertions pass when suggestions are recorded.
        """
        registry = ToolRegistry(".", questioner=lambda q, opts: "")
        registry.execute(
            "suggest",
            {"options": ["Find local experts", "Find local class"]},
        )
        self.assertEqual(
            registry.suggestions,
            ["Find local experts", "Find local class"],
        )

    def _names(self, registry: ToolRegistry) -> list[str]:
        """Return advertised tool names.

        Parameters
        ----------
        registry : ToolRegistry
            Tool registry to inspect.

        Returns
        -------
        list[str]
            Advertised tool names.
        """
        return [item["function"]["name"] for item in registry.schema()]


class ToolCallClient:
    """Return one write call followed by final text."""

    def __init__(self) -> None:
        """Initialize the call counter.

        Returns
        -------
        None
            This initializer configures the fake client.
        """
        self.calls = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return a deterministic tool-call sequence.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages.
        tools : list[dict]
            Advertised tool schemas.

        Returns
        -------
        dict
            OpenAI-compatible response body.
        """
        self.calls += 1
        if self.calls == 1:
            return {"choices": [{"message": self._write_message()}]}
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "App created"}}
            ]
        }

    def _write_message(self) -> dict:
        """Build the write tool-call message.

        Returns
        -------
        dict
            Assistant message containing one write call.
        """
        arguments = (
            '{"path": "index.html", "content": "<h1>Minimal Harness</h1>"}'
        )
        call = {
            "id": "call-1",
            "function": {"name": "write", "arguments": arguments},
        }
        return {"role": "assistant", "content": None, "tool_calls": [call]}


if __name__ == "__main__":
    unittest.main()
