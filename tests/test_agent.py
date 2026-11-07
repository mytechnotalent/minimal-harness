"""Tests for the Pi-like interactive tool runtime."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class LoopingClient:
    """Return one tool call, then a final answer."""

    def __init__(self) -> None:
        """Initialize the call counter."""
        self.calls = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return a tool call first and text second."""
        self.calls += 1
        return self._tool_call() if self.calls == 1 else self._final()

    def _tool_call(self) -> dict:
        """Return one read tool call."""
        call = {
            "id": "1",
            "function": {"name": "read", "arguments": '{"path": "x"}'},
        }
        message = {"role": "assistant", "content": "", "tool_calls": [call]}
        return {"choices": [{"message": message}]}

    def _final(self) -> dict:
        """Return a final text response."""
        message = {"role": "assistant", "content": "final answer"}
        return {"choices": [{"message": message}]}


class ReviewClient:
    """Return a draft answer and a fixed review response."""

    def __init__(self, review: str) -> None:
        """Store the review response.

        Parameters
        ----------
        review : str
            Raw review text.

        Returns
        -------
        None
            The client is ready.
        """
        self.review = review
        self.complete_calls = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return a draft final answer."""
        message = {"role": "assistant", "content": "draft answer"}
        return {"choices": [{"message": message}]}

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return the configured review text."""
        self.complete_calls += 1
        return self.review


class AnswerReviewTests(unittest.TestCase):
    """Verify adversarial review of final answers."""

    def test_approved_answer_is_kept(self) -> None:
        """An approved draft is returned unchanged."""
        client = ReviewClient('{"approved": true, "issues": []}')
        agent = Agent(root=".", client=client, max_turns=1)
        self.assertEqual(agent.run("question"), "draft answer")

    def test_rejected_answer_is_revised(self) -> None:
        """A rejected draft is replaced by the revised answer."""
        review = json.dumps(
            {
                "approved": False,
                "issues": ["unsupported claim"],
                "revised_answer": "better answer",
            }
        )
        agent = Agent(root=".", client=ReviewClient(review), max_turns=1)
        self.assertEqual(agent.run("question"), "better answer")

    def test_invalid_review_keeps_answer(self) -> None:
        """An invalid review does not break the answer."""
        agent = Agent(root=".", client=ReviewClient("not json"), max_turns=1)
        self.assertEqual(agent.run("question"), "draft answer")

    def test_review_can_be_disabled(self) -> None:
        """The environment can disable answer review."""
        client = ReviewClient('{"approved": false}')
        agent = Agent(root=".", client=client, max_turns=1)
        with patch.dict(os.environ, {"HARNESS_ANSWER_REVIEW": "0"}):
            self.assertEqual(agent.run("question"), "draft answer")
        self.assertEqual(client.complete_calls, 0)


class CodingStandardsTests(unittest.TestCase):
    """Verify the agent receives the mandatory language standards."""

    def test_system_prompt_includes_standards(self) -> None:
        """Python, C, Rust, and assembly rules are always present."""
        agent = Agent(root=".")
        system = agent.messages[0]["content"]
        self.assertIn("Mandatory coding standards", system)
        self.assertIn("REA conventions", system)
        self.assertIn("embedded C standard", system)
        self.assertIn("RP2350 RISC-V", system)


class AgentLimitTests(unittest.TestCase):
    """Verify turn-limit finalization and tool visibility."""

    def test_turn_limit_requests_final_answer(self) -> None:
        """The agent asks for a final answer after the turn limit."""
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "x").write_text("ok", encoding="utf-8")
            agent = Agent(root=directory, client=LoopingClient(), max_turns=1)
            self.assertEqual(agent.run("question"), "final answer")

    def test_unadvertised_tool_is_rejected(self) -> None:
        """A tool hidden from the model cannot be executed."""
        registry = ToolRegistry(".")
        with self.assertRaises(ToolError):
            registry.execute("ask", {"question": "Pick", "options": ["a"]})


class InstallGuardTests(unittest.TestCase):
    """Verify package-install commands prompt for approval."""

    def test_install_command_detected(self) -> None:
        """Common install commands are recognized.

        Returns
        -------
        None
            Assertions pass when both forms are detected.
        """
        registry = ToolRegistry(".")
        for command in (
            "pip install reportlab",
            "python -m pip install reportlab",
            "npm install axios",
            "yarn add axios",
            "pnpm add axios",
            "brew install jq",
            "playwright install chromium",
            "cargo install ripgrep",
        ):
            self.assertTrue(registry._is_install(command))

    def test_plain_command_not_detected(self) -> None:
        """Non-install commands are not flagged.

        Returns
        -------
        None
            Assertions pass when the command is ignored.
        """
        registry = ToolRegistry(".")
        self.assertFalse(registry._is_install("python script.py"))
        self.assertFalse(registry._is_install("ls -la"))

    def test_install_requires_approval(self) -> None:
        """An install command asks the questioner first.

        Returns
        -------
        None
            Assertions pass when approval is requested.
        """
        asked = []

        def questioner(question, options):
            asked.append((question, options))
            return "No, don't install"

        registry = ToolRegistry(".", questioner=questioner)
        with self.assertRaises(ToolError):
            registry.bash("pip install reportlab")
        self.assertEqual(len(asked), 1)
        self.assertIn("install", asked[0][0].lower())
        self.assertIn("Yes, install it", asked[0][1])

    def test_install_approval_missing_raises(self) -> None:
        """Without a questioner the install is rejected.

        Returns
        -------
        None
            Assertions pass when a ToolError is raised.
        """
        registry = ToolRegistry(".")
        with self.assertRaises(ToolError):
            registry.bash("pip install reportlab")


class ProjectFolderGuardTests(unittest.TestCase):
    """Verify new project files require a named folder."""

    def test_root_file_is_rejected(self) -> None:
        """A new file directly under the workspace is refused."""
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(directory, require_project_folder=True)
            with self.assertRaises(ToolError):
                registry.write("index.html", "x")

    def test_project_folder_is_allowed(self) -> None:
        """A file inside a project folder is accepted."""
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(directory, require_project_folder=True)
            result = registry.write("game/index.html", "x")
        self.assertEqual(result["path"], "game/index.html")

    def test_protected_source_tree_is_rejected(self) -> None:
        """New files in the harness source tree are refused."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "meta_harness").mkdir()
            registry = ToolRegistry(directory, require_project_folder=True)
            with self.assertRaises(ToolError):
                registry.write("meta_harness/extra.py", "x")

    def test_default_allows_root_writes(self) -> None:
        """Without the guard, root-level writes still work."""
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(directory)
            result = registry.write("index.html", "x")
        self.assertEqual(result["path"], "index.html")


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
