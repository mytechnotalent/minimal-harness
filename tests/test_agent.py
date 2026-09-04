"""Tests for the Pi-like interactive tool runtime."""

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
