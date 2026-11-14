"""Tests for the Pi-like interactive tool runtime."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meta_harness.agent import Agent
from meta_harness.agent import _repair_attempts
from meta_harness.session import Session
from meta_harness.tools import ToolError
from meta_harness.tools import ToolRegistry
from meta_harness.tools import _compact_test_output


class AgentTests(unittest.TestCase):
    """Verify model-driven tool execution and workspace safety."""

    def test_agent_executes_write_then_returns_final_text(self) -> None:
        """Execute a model-requested write before final response.

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when suggestions are recorded.
        """
        expected = ["Find local experts", "Find local class"]
        registry = ToolRegistry(".", questioner=lambda q, opts: "")
        registry.execute("suggest", {"options": expected})
        self.assertEqual(registry.suggestions, expected)

    def test_web_tools_can_be_disabled(self) -> None:
        """Web and browser tools are hidden when disabled.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        registry = ToolRegistry(".", web_enabled=False)
        names = self._names(registry)
        self.assertNotIn("web_search", names)
        self.assertIn("read", names)

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


class ToolOutputTests(unittest.TestCase):
    """Verify oversized tool output is clipped before it reaches the model."""

    def test_read_output_is_truncated(self) -> None:
        """A large file result is wrapped with a bounded payload.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        raw = _read_output()
        value = json.loads(raw)
        self.assertTrue(value["truncated"])
        self.assertLessEqual(len(value["output"]), 2100)
        self.assertIn("...[truncated]...", value["output"])


class WorkspaceSearchTests(unittest.TestCase):
    """Verify repository search and patch tools."""

    def test_glob_and_repo_map_find_files(self) -> None:
        """Glob and repo map list nested source files.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _workspace_file(root, "src/a.py", "x = 1\n")
            registry = ToolRegistry(root)
            globbed = registry.glob("**/*.py")
            mapped = registry.repo_map()
        self.assertEqual(globbed["files"], ["src/a.py"])
        self.assertEqual(mapped["files"], ["src/a.py"])

    def test_grep_and_list_report_workspace_entries(self) -> None:
        """Grep finds lines and list reports directory entries.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _workspace_file(root, "src/a.py", "value = 42\n")
            registry = ToolRegistry(root)
            found = registry.grep("42")
            listed = registry.list("src")
        self.assertEqual(found["matches"][0]["line"], 1)
        self.assertEqual(listed["entries"][0]["name"], "a.py")

    def test_edit_accepts_whitespace_variant(self) -> None:
        """A whitespace-insensitive match still edits safely.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _workspace_file(
                root, "a.py", "def  add(a, b):\n    return a + b\n"
            )
            registry = ToolRegistry(root)
            registry.edit("a.py", "def add(a, b):", "def add(a, b, c):")
            self.assertIn("def add(a, b, c):", path.read_text())

    def test_edit_reports_duplicate_match(self) -> None:
        """A repeated fragment is rejected with a line hint.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _workspace_file(root, "a.py", "same\nsame\n")
            registry = ToolRegistry(root)
            with self.assertRaises(ToolError) as raised:
                registry.edit("a.py", "same", "other")
        self.assertIn("not unique", str(raised.exception))

    def test_patch_applies_multiple_edits(self) -> None:
        """A patch applies every fragment in one call.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _workspace_file(root, "a.py", "one = 1\ntwo = 2\n")
            registry = ToolRegistry(root)
            result = registry.patch("a.py", _two_edits())
            content = path.read_text()
        self.assertEqual(result["replacements"], 2)
        self.assertIn("one = 10", content)

    def test_test_output_is_compacted(self) -> None:
        """Long test logs keep only failure lines.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        text = "noise\n" * 5000 + "FAILED test_x - AssertionError\n"
        compact = _compact_test_output(text)
        self.assertIn("FAILED test_x", compact)
        self.assertLess(len(compact), 5000)


class EditNudgeTests(unittest.TestCase):
    """Verify exploration is cut off with an edit nudge."""

    def test_nudge_restricts_tools(self) -> None:
        """After three quiet turns only edit tools are advertised.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(root=".", client=object())
        agent._maybe_nudge(3)
        names = {item["function"]["name"] for item in agent._tool_schemas(3)}
        self.assertEqual(names, {"edit", "write", "patch"})

    def test_nudge_blocks_non_edit_tools(self) -> None:
        """Non-edit tools fail until a file is modified.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(root=".", client=object())
        agent._nudged = True
        call = {"id": "1", "function": {"name": "bash", "arguments": "{}"}}
        result = agent._tool_result(call)
        self.assertIn("unavailable", result["content"])

    def test_bash_blocks_outside_paths(self) -> None:
        """Shell commands cannot escape the workspace.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(directory)
            with self.assertRaises(ToolError):
                registry.bash("find / -name signer.py")


class LoopingClient:
    """Return one tool call, then a final answer."""

    def __init__(self) -> None:
        """Initialize the call counter.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.calls = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return a tool call first and text second.

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
        return self._tool_call() if self.calls == 1 else self._final()

    def _tool_call(self) -> dict:
        """Return one read tool call.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Response containing one tool call.
        """
        call = {
            "id": "1",
            "function": {"name": "read", "arguments": '{"path": "x"}'},
        }
        message = {"role": "assistant", "content": "", "tool_calls": [call]}
        return {"choices": [{"message": message}]}

    def _final(self) -> dict:
        """Return a final text response.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Response containing final text.
        """
        message = {"role": "assistant", "content": "final answer"}
        return {"choices": [{"message": message}]}


class ReviewClient:
    """Return a draft answer and a fixed review response."""

    def __init__(self, review: str, draft: str = "draft answer") -> None:
        """Store the review response and draft answer.

        Parameters
        ----------
        review : str
            Raw review text.
        draft : str
            Draft answer returned by :meth:`chat`.

        Returns
        -------
        None
            The client is ready.
        """
        self.review = review
        self.draft = draft
        self.complete_calls = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return a draft final answer.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages.

        tools : list[dict]
            Advertised tool schemas.

        Returns
        -------
        dict
            Response containing the draft answer.
        """
        message = {"role": "assistant", "content": self.draft}
        return {"choices": [{"message": message}]}

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return the configured review text.

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
            Raw review text.
        """
        self.complete_calls += 1
        return self.review


class RecordingClient:
    """Record chat requests and return a fixed final answer."""

    def __init__(self) -> None:
        """Initialize an empty recording.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The client is ready.
        """
        self.messages: list[dict] = []
        self.calls = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Record the request and return final text.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages.

        tools : list[dict]
            Advertised tool schemas.

        Returns
        -------
        dict
            Response containing final text.
        """
        self.messages = messages
        self.calls += 1
        message = {"role": "assistant", "content": "final answer"}
        return {"choices": [{"message": message}]}


class AnswerReviewTests(unittest.TestCase):
    """Verify adversarial review of final answers."""

    def test_approved_answer_is_kept(self) -> None:
        """An approved draft is returned unchanged.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = ReviewClient('{"approved": true, "issues": []}')
        agent = Agent(root=".", client=client, max_turns=1)
        self.assertEqual(agent.run("question"), "draft answer")

    def test_rejected_answer_is_revised(self) -> None:
        """A rejected draft is replaced by the revised answer.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        review = _rejected_review()
        agent = Agent(root=".", client=ReviewClient(review), max_turns=1)
        self.assertEqual(agent.run("question"), "better answer")

    def test_invalid_review_keeps_answer(self) -> None:
        """An invalid review does not break the answer.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(root=".", client=ReviewClient("not json"), max_turns=1)
        self.assertEqual(agent.run("question"), "draft answer")

    def test_review_can_be_disabled(self) -> None:
        """The environment can disable answer review.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = ReviewClient('{"approved": false}')
        agent = Agent(root=".", client=client, max_turns=1)
        with patch.dict(os.environ, {"HARNESS_ANSWER_REVIEW": "0"}):
            self.assertEqual(agent.run("question"), "draft answer")
        self.assertEqual(client.complete_calls, 0)

    def test_auto_review_skips_short_untooled_answer(self) -> None:
        """Auto mode skips review for short answers without tools.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = ReviewClient('{"approved": false}')
        agent = Agent(root=".", client=client, max_turns=1)
        with patch.dict(os.environ, {"HARNESS_ANSWER_REVIEW": "auto"}):
            self.assertEqual(agent.run("question"), "draft answer")
        self.assertEqual(client.complete_calls, 0)

    def test_auto_review_checks_long_answer(self) -> None:
        """Auto mode reviews a long unsupported answer.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = ReviewClient('{"approved": true}', draft="x" * 500)
        agent = Agent(root=".", client=client, max_turns=1)
        with patch.dict(os.environ, {"HARNESS_ANSWER_REVIEW": "auto"}):
            agent.run("question")
        self.assertEqual(client.complete_calls, 1)


class CodingStandardsTests(unittest.TestCase):
    """Verify the agent receives the mandatory language standards."""

    def test_system_prompt_describes_voice_input(self) -> None:
        """The agent knows the app transcribes its press-to-talk audio.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(root=".")
        system = agent.messages[0]["content"].lower()
        self.assertIn("press-to-talk", system)
        self.assertIn("transcribes", system)
        self.assertIn("never claim", system)

    def test_system_prompt_falls_back_when_browser_fails(self) -> None:
        """The agent answers from search results if browsing fails.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(root=".")
        system = agent.messages[0]["content"]
        self.assertIn("browser_open", system)
        self.assertIn("web_search", system)

    def test_system_prompt_includes_standards(self) -> None:
        """Python, C, Rust, and assembly rules start in the prompt.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(root=".")
        system = agent.messages[0]["content"]
        self.assertIn("Mandatory coding standards", system)
        self.assertIn("REA conventions", system)
        self.assertIn("embedded C standard", system)
        self.assertIn("RP2350 RISC-V", system)

    def test_standards_strip_for_non_coding_prompt(self) -> None:
        """Auto mode removes standards from a plain question.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = RecordingClient()
        agent = Agent(root=".", client=client)
        agent.run("What is the capital of France?")
        system = client.messages[0]["content"]
        self.assertNotIn("Mandatory coding standards", system)
        self.assertIn("ask", system.lower())

    def test_standards_kept_for_coding_prompt(self) -> None:
        """Auto mode keeps standards for a coding task.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = RecordingClient()
        agent = Agent(root=".", client=client)
        agent.run("Write a python function that adds two numbers.")
        system = client.messages[0]["content"]
        self.assertIn("Mandatory coding standards", system)


class ContextCompactionTests(unittest.TestCase):
    """Verify long conversations are compacted before model calls."""

    def test_compaction_drops_orphan_tool_messages(self) -> None:
        """Compaction keeps the system prompt and complete recent turns.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(".", client=object())
        agent.messages = _orphan_messages()
        agent._compact_messages(2)
        self._assert_compacted(agent)

    def _assert_compacted(self, agent) -> None:
        """Verify orphan tool messages are dropped.

        Parameters
        ----------
        agent : Agent
            Agent whose messages were compacted.

        Returns
        -------
        None
            Assertions document the result.
        """
        roles = [item["role"] for item in agent.messages]
        self.assertEqual(roles, ["system", "assistant"])
        self.assertEqual(agent.messages[0]["content"], "sys")

    def test_auto_compaction_respects_budget(self) -> None:
        """A low character budget triggers compaction.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(".", client=object())
        agent.messages = _budget_messages()
        with patch.dict(os.environ, _low_budget()):
            agent._maybe_compact()
        self.assertEqual(len(agent.messages), 2)
        self.assertEqual(agent.messages[0]["role"], "system")

    def test_compaction_skips_short_conversations(self) -> None:
        """A conversation under budget is left untouched.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(".", client=object())
        before = agent.messages[:]
        with patch.dict(os.environ, {"HARNESS_CONTEXT_CHARS": "999999"}):
            agent._maybe_compact()
        self.assertEqual(agent.messages, before)

    def test_trim_context_keeps_system(self) -> None:
        """Trimming keeps the system prompt and newest messages.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(".", client=object())
        agent.messages = _trim_messages()
        agent.trim_context(1)
        roles = [item["role"] for item in agent.messages]
        self.assertEqual(roles, ["system", "assistant"])


class AgentLimitTests(unittest.TestCase):
    """Verify turn-limit finalization and tool visibility."""

    def test_turn_limit_requests_final_answer(self) -> None:
        """The agent asks for a final answer after the turn limit.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "x").write_text("ok", encoding="utf-8")
            agent = Agent(root=directory, client=LoopingClient(), max_turns=1)
            self.assertEqual(agent.run("question"), "final answer")

    def test_unadvertised_tool_is_rejected(self) -> None:
        """A tool hidden from the model cannot be executed.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        registry = ToolRegistry(".")
        with self.assertRaises(ToolError):
            registry.execute("ask", {"question": "Pick", "options": ["a"]})


class BadArgsClient:
    """Return a tool call with malformed JSON, then a final answer."""

    def __init__(self) -> None:
        """Initialize the call counter.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.calls = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return a broken tool call first and text second.

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
            return _broken_call()
        return _final_answer("ok")


class ToolCallRepairTests(unittest.TestCase):
    """Verify malformed tool-call arguments cannot poison a request."""

    def test_loaded_tool_calls_are_repaired(self) -> None:
        """Invalid arguments in a saved session become an empty object.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        bad = _bad_session_message()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "s.jsonl")
            path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
            args = _repaired_args(directory, path)
        self.assertEqual(args, "{}")

    def test_model_tool_calls_are_repaired(self) -> None:
        """Invalid arguments returned by the model are repaired.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            session = Session(Path(directory, "s.jsonl"))
            agent = Agent(directory, client=BadArgsClient(), session=session)
            agent.run("go")
            args = session.messages[1]["tool_calls"][0]["function"][
                "arguments"
            ]
        self.assertEqual(args, "{}")


class InstallGuardTests(unittest.TestCase):
    """Verify package-install commands prompt for approval."""

    def test_install_command_detected(self) -> None:
        """Common install commands are recognized.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when both forms are detected.
        """
        registry = ToolRegistry(".")
        for command in _INSTALL_COMMANDS:
            self.assertTrue(registry._is_install(command))

    def test_plain_command_not_detected(self) -> None:
        """Non-install commands are not flagged.

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when approval is requested.
        """
        asked = []
        registry = ToolRegistry(".", questioner=_RecordingQuestioner(asked))
        with self.assertRaises(ToolError):
            registry.bash("pip install reportlab")
        self.assertEqual(len(asked), 1)
        self.assertIn("install", asked[0][0].lower())
        self.assertIn("Yes, install it", asked[0][1])

    def test_install_approval_missing_raises(self) -> None:
        """Without a questioner the install is rejected.

        Parameters
        ----------
        None

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
        """A new file directly under the workspace is refused.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(directory, require_project_folder=True)
            with self.assertRaises(ToolError):
                registry.write("index.html", "x")

    def test_project_folder_is_allowed(self) -> None:
        """A file inside a project folder is accepted.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(directory, require_project_folder=True)
            result = registry.write("game/index.html", "x")
        self.assertEqual(result["path"], "game/index.html")

    def test_protected_source_tree_is_rejected(self) -> None:
        """New files in the harness source tree are refused.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "meta_harness").mkdir()
            registry = ToolRegistry(directory, require_project_folder=True)
            with self.assertRaises(ToolError):
                registry.write("meta_harness/extra.py", "x")

    def test_default_allows_root_writes(self) -> None:
        """Without the guard, root-level writes still work.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(directory)
            result = registry.write("index.html", "x")
        self.assertEqual(result["path"], "index.html")


class ToolCallClient:
    """Return one write call followed by final text."""

    def __init__(self) -> None:
        """Initialize the call counter.

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

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


class LeanModeTests(unittest.TestCase):
    """Verify the lean repo-editing prompt."""

    def test_lean_uses_short_prompt(self) -> None:
        """Lean mode loads only the short prompt.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(".", client=object(), lean=True)
        system = agent.messages[0]["content"]
        self.assertIn("fewest possible turns", system)
        self.assertNotIn("coding standards", system.lower())

    def test_lean_trim_is_noop(self) -> None:
        """Lean mode never strips its system prompt.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(".", client=object(), lean=True)
        before = agent.messages[0]["content"]
        agent._trim_system("write a script")
        self.assertEqual(agent.messages[0]["content"], before)


class MutationReviewTests(unittest.TestCase):
    """Verify file edits skip the text-only answer review."""

    def test_mutated_run_skips_review(self) -> None:
        """A file edit makes answer review unnecessary.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(".", client=object())
        agent._mutated = True
        self.assertEqual(agent._review_answer("q", "a"), "a")

    def test_begin_run_resets_mutation(self) -> None:
        """Starting a run clears the mutation flag.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        agent = Agent(".", client=object())
        agent._mutated = True
        agent._begin_run("next")
        self.assertFalse(agent._mutated)


if __name__ == "__main__":
    unittest.main()


_INSTALL_COMMANDS = (
    "pip install reportlab",
    "python -m pip install reportlab",
    "npm install axios",
    "yarn add axios",
    "pnpm add axios",
    "brew install jq",
    "playwright install chromium",
    "cargo install ripgrep",
)


def _rejected_review() -> str:
    """Return a JSON review that rejects the draft.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Raw review JSON with a revised answer.
    """
    return json.dumps(
        {
            "approved": False,
            "issues": ["unsupported claim"],
            "revised_answer": "better answer",
        }
    )


def _two_edits() -> list[dict[str, str]]:
    """Return two simple edits for patch tests.

    Parameters
    ----------
    None

    Returns
    -------
    list[dict[str, str]]
        Old and new fragments.
    """
    return [
        {"old": "one = 1", "new": "one = 10"},
        {"old": "two = 2", "new": "two = 20"},
    ]


def _workspace_file(root: Path, relative: str, text: str) -> Path:
    """Write a file inside a temporary workspace.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    relative : str
        Relative file path.
    text : str
        File content.

    Returns
    -------
    pathlib.Path
        Written file path.
    """
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _read_output() -> str:
    """Read a large file through the tool registry.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Serialized tool result.
    """
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "big.txt").write_text("x" * 20000)
        limit = {"HARNESS_TOOL_OUTPUT_LIMIT": "2000"}
        with patch.dict(os.environ, limit):
            return ToolRegistry(root).execute("read", {"path": "big.txt"})


def _orphan_messages() -> list[dict]:
    """Build messages with a leading orphan tool result.

    Parameters
    ----------
    None

    Returns
    -------
    list of dict
        Conversation messages.
    """
    return [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "reply"},
        {"role": "tool", "tool_call_id": "1", "content": "result"},
        {"role": "assistant", "content": "new"},
    ]


def _budget_messages() -> list[dict]:
    """Build messages that exceed the compaction budget.

    Parameters
    ----------
    None

    Returns
    -------
    list of dict
        Conversation messages with long content.
    """
    return [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "x" * 200},
        {"role": "assistant", "content": "y" * 200},
    ]


def _low_budget() -> dict:
    """Return a tight compaction budget environment.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Character and keep-count settings.
    """
    return {
        "HARNESS_CONTEXT_CHARS": "100",
        "HARNESS_CONTEXT_KEEP": "1",
    }


def _trim_messages() -> list[dict]:
    """Build a short conversation for trimming.

    Parameters
    ----------
    None

    Returns
    -------
    list of dict
        Conversation messages.
    """
    return [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "new"},
    ]


def _broken_call() -> dict:
    """Build a response with malformed tool-call arguments.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        OpenAI-compatible response body.
    """
    call = {"id": "1", "function": {"name": "read", "arguments": '{"p'}}
    message = {"role": "assistant", "content": "", "tool_calls": [call]}
    return {"choices": [{"message": message}]}


def _final_answer(content: str) -> dict:
    """Build a response with a final text answer.

    Parameters
    ----------
    content : str
        Assistant answer text.

    Returns
    -------
    dict
        OpenAI-compatible response body.
    """
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    }


def _bad_session_message() -> dict:
    """Build an assistant message with malformed tool arguments.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Session message with broken arguments.
    """
    call = {"id": "1", "function": {"name": "read", "arguments": '{"p'}}
    return {"role": "assistant", "content": "", "tool_calls": [call]}


def _repaired_args(directory, path) -> str:
    """Load a session and return the repaired arguments.

    Parameters
    ----------
    directory : str
        Temporary workspace directory.

    path : pathlib.Path
        Session transcript path.

    Returns
    -------
    str
        Repaired tool-call arguments.
    """
    agent = Agent(directory, client=BadArgsClient(), session=Session(path))
    return agent.messages[-1]["tool_calls"][0]["function"]["arguments"]


class _RecordingQuestioner:
    """Record questions and decline package installs."""

    def __init__(self, asked: list) -> None:
        """Store the recording list.

        Parameters
        ----------
        asked : list
            List receiving (question, options) pairs.

        Returns
        -------
        None
            The questioner is ready.
        """
        self.asked = asked

    def __call__(self, question, options):
        """Record the question and decline.

        Parameters
        ----------
        question : str
            Question text.

        options : list[str]
            Suggested answers.

        Returns
        -------
        str
            Decline answer.
        """
        self.asked.append((question, options))
        return "No, don't install"


if __name__ == "__main__":
    unittest.main()


class RepairBudgetTests(unittest.TestCase):
    """Verify the bounded reviewer-test repair budget."""

    def test_repair_attempts_is_bounded(self) -> None:
        """The repair count is positive and tolerant of bad input.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {"HARNESS_REPAIR_ATTEMPTS": "3"}):
            self.assertEqual(_repair_attempts(), 3)
        with patch.dict(os.environ, {"HARNESS_REPAIR_ATTEMPTS": "0"}):
            self.assertEqual(_repair_attempts(), 1)
        with patch.dict(os.environ, {"HARNESS_REPAIR_ATTEMPTS": "bad"}):
            self.assertEqual(_repair_attempts(), 2)
