"""Pi-like stateful tool-calling agent runtime."""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ._json_util import json_value
from .openrouter import OpenRouterClient
from .prompts import load as _load_prompt
from .session import Session
from .task_evaluator import run_workspace_tests
from .tools import ToolError
from .tools import ToolRegistry

_CONTEXT_CHARS = 60000
_CONTEXT_KEEP = 16
_CODING_WORDS = (
    "code",
    "function",
    "class",
    "bug",
    "fix",
    "test",
    "script",
    "implement",
    "refactor",
    "debug",
    "file",
    "api",
    "html",
    "css",
    "javascript",
    "python",
    "rust",
    "firmware",
    "sql",
    "build",
)


def _int_env(name: str, default: int) -> int:
    """Return a positive integer environment setting.

    Parameters
    ----------
    name : str
        Variable name.
    default : int
        Fallback value.

    Returns
    -------
    int
        Parsed positive value, or the fallback.
    """
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _message_chars(messages: list[dict[str, Any]]) -> int:
    """Return the approximate character size of a conversation.

    Parameters
    ----------
    messages : list[dict[str, Any]]
        Conversation messages.

    Returns
    -------
    int
        Total serialized characters.
    """
    return sum(len(json.dumps(item, default=str)) for item in messages)


def _standards_mode() -> str:
    """Return the coding-standards inclusion mode.

    Parameters
    ----------
    None

    Returns
    -------
    str
        ``"keep"``, ``"strip"``, or ``"auto"``.
    """
    value = os.getenv("HARNESS_CODING_STANDARDS", "auto").strip().lower()
    if value in ("1", "true", "yes", "on"):
        return "keep"
    if value in ("0", "false", "no", "off"):
        return "strip"
    return "auto"


def _coding_task(prompt: str) -> bool:
    """Return whether a prompt likely needs coding standards.

    Parameters
    ----------
    prompt : str
        User task.

    Returns
    -------
    bool
        ``True`` for likely coding tasks.
    """
    words = set(re.findall(r"[a-z]+", prompt.lower()))
    return bool(words & set(_CODING_WORDS))


class Agent:
    """Run a bounded conversation with model-invoked tools."""

    def __init__(
        self,
        root: Path | str = ".",
        client: OpenRouterClient | None = None,
        max_turns: int = 12,
        session: Session | None = None,
        observer=None,
    ) -> None:
        """Initialize an agent session.

        Parameters
        ----------
        root : pathlib.Path or str
            Workspace root.
        client : OpenRouterClient or None
            Optional model client.
        max_turns : int
            Maximum model turns.
        session : Session or None
            Optional persisted session.
        observer : callable or None
            Optional callback run after each tool call.

        Returns
        -------
        None
            This initializer configures the agent.
        """
        self.observer = observer
        self.client = client or OpenRouterClient()
        self.tools = ToolRegistry(root)
        self.max_turns = max_turns
        self.session = session
        self.messages: list[dict[str, Any]] = self._initial_messages(session)
        self.steering: list[str] = []
        self.follow_up: list[str] = []

    def _initial_messages(
        self, session: Session | None
    ) -> list[dict[str, Any]]:
        """Copy messages from an optional session.

        Parameters
        ----------
        session : Session or None
            Optional persisted session.

        Returns
        -------
        list[dict[str, Any]]
            Initial conversation messages.
        """
        messages = session.messages[:] if session else []
        for message in messages:
            _repair_tool_calls(message)
        if messages and messages[0].get("role") == "system":
            return messages
        return [{"role": "system", "content": _system_prompt()}] + messages

    def run(self, prompt: str) -> str:
        """Run the agent until final text or turn limit.

        Parameters
        ----------
        prompt : str
            User task.

        Returns
        -------
        str
            Final assistant response.
        """
        if _adversarial_drafts() > 1 and hasattr(self.client, "complete"):
            return self._adversarial_run(prompt)
        self._append({"role": "user", "content": prompt})
        self._trim_system(prompt)
        answer = self._loop()
        answer = self._verified_answer(prompt, answer)
        return self._review_answer(prompt, answer)

    def _verified_answer(self, prompt: str, answer: str) -> str:
        """Run reviewer tests and apply one repair turn.

        Parameters
        ----------
        prompt : str
            User task.

        answer : str
            Draft answer.

        Returns
        -------
        str
            Original or repaired answer.
        """
        if not _answer_tests_enabled() or not hasattr(self.client, "complete"):
            return answer
        tests = self._workspace_tests(prompt, answer)
        if not tests:
            return answer
        return self._repair_if_failing(tests, answer)

    def _repair_if_failing(self, tests, answer: str) -> str:
        """Run tests and repair the workspace once on failure.

        Parameters
        ----------
        tests : list[str]
            Reviewer-generated unittest sources.

        answer : str
            Draft answer.

        Returns
        -------
        str
            Original answer when tests pass, otherwise a repaired answer.
        """
        passed, output = run_workspace_tests(self.tools.root, tests)
        if passed:
            return answer
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = _snapshot(Path(temporary), self.tools.root)
            self._append(_repair_message(output))
            repaired = self._loop()
            return self._accept_repair(tests, repaired, answer, snapshot)

    def _accept_repair(self, tests, repaired, answer, snapshot) -> str:
        """Accept a repair only when reviewer tests now pass.

        Parameters
        ----------
        tests : list[str]
            Reviewer-generated unittest sources.

        repaired : str
            Repaired answer.

        answer : str
            Original answer.

        snapshot : pathlib.Path
            Workspace snapshot.

        Returns
        -------
        str
            Repaired answer when tests pass, otherwise the original.
        """
        fixed, _ = run_workspace_tests(self.tools.root, tests)
        if fixed:
            return repaired
        _restore_workspace(self.tools.root, snapshot)
        return answer

    def _workspace_tests(self, prompt: str, answer: str) -> list[str]:
        """Ask the reviewer for executable workspace tests.

        Parameters
        ----------
        prompt : str
            User task.

        answer : str
            Agent's draft answer.

        Returns
        -------
        list[str]
            Reviewer-generated unittest sources.
        """
        context = _workspace_context(prompt, answer, self.tools.root)
        try:
            raw = self.client.complete(_load_prompt("repo_reviewer"), context)
        except Exception:
            return []
        return _test_sources(raw)

    def _adversarial_run(self, prompt: str) -> str:
        """Generate drafts, adjudicate, and review the best answer.

        Parameters
        ----------
        prompt : str
            User task.

        Returns
        -------
        str
            Reviewed best draft.
        """
        self._append({"role": "user", "content": prompt})
        self._trim_system(prompt)
        base = _copy_messages(self.messages)
        drafts = self._drafts(base)
        best = self._pick_draft(prompt, drafts)
        self.messages = _copy_messages(base)
        self._append({"role": "assistant", "content": best})
        return self._review_answer(prompt, best)

    def _drafts(self, base: list[dict]) -> list[str]:
        """Run independent draft loops without touching the session.

        Parameters
        ----------
        base : list[dict]
            Base conversation messages.

        Returns
        -------
        list[str]
            One final answer per draft.
        """
        session = self.session
        self.session = None
        try:
            return self._run_drafts(base)
        finally:
            self.session = session

    def _run_drafts(self, base: list[dict]) -> list[str]:
        """Run the configured number of draft loops.

        Parameters
        ----------
        base : list[dict]
            Base conversation messages.

        Returns
        -------
        list[str]
            One final answer per draft.
        """
        drafts = []
        for _ in range(_adversarial_drafts()):
            self.messages = _copy_messages(base)
            drafts.append(self._loop())
        return drafts

    def _pick_draft(self, prompt: str, drafts: list[str]) -> str:
        """Ask the adjudicator model to choose the best draft.

        Parameters
        ----------
        prompt : str
            User task.

        drafts : list[str]
            Candidate final answers.

        Returns
        -------
        str
            Chosen draft, defaulting to the first.
        """
        try:
            raw = self.client.complete(
                _load_prompt("adversarial"), _draft_context(prompt, drafts)
            )
        except Exception:
            return drafts[0]
        return _chosen_draft(raw, drafts)

    def _trim_system(self, prompt: str) -> None:
        """Drop coding standards for non-coding tasks when configured.

        Parameters
        ----------
        prompt : str
            User task.

        Returns
        -------
        None
            The system message may be shortened in place.
        """
        mode = _standards_mode()
        if mode == "keep":
            return
        if mode == "auto" and _coding_task(prompt):
            return
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = _load_prompt("agent")

    def _review_answer(self, prompt: str, answer: str) -> str:
        """Adversarially review and possibly revise a final answer.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft final answer.

        Returns
        -------
        str
            Approved answer or a revised answer.
        """
        if not self._review_enabled(answer):
            return answer
        review = self._answer_review(prompt, answer)
        revised = review.get("revised_answer")
        if self._rejected(review) and isinstance(revised, str):
            return revised.strip() or answer
        return answer

    def _review_enabled(self, answer: str = "") -> bool:
        """Return whether answer review is enabled.

        Parameters
        ----------
        answer : str
            Draft answer used by ``auto`` mode.

        Returns
        -------
        bool
            ``True`` when configured and the client supports completion.
        """
        mode = os.getenv("HARNESS_ANSWER_REVIEW", "1").strip().lower()
        if not hasattr(self.client, "complete"):
            return False
        if mode in ("0", "false", "no", "off"):
            return False
        if mode == "auto":
            return self._needs_review(answer)
        return True

    def _needs_review(self, answer: str) -> bool:
        """Return whether an answer is substantial enough to review.

        Parameters
        ----------
        answer : str
            Draft answer.

        Returns
        -------
        bool
            ``True`` when tools were used or the answer is long.
        """
        if any(item.get("role") == "tool" for item in self.messages):
            return True
        return len(answer.strip()) >= 400

    def _answer_review(self, prompt: str, answer: str) -> dict:
        """Request one structured answer review.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft final answer.

        Returns
        -------
        dict
            Decoded review, or an empty dict on failure.
        """
        try:
            raw = self._review_raw(prompt, answer)
            value = json_value(raw)
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    def _review_raw(self, prompt: str, answer: str) -> str:
        """Request the raw reviewer response.

        Parameters
        ----------
        prompt : str
            User question.

        answer : str
            Draft final answer.

        Returns
        -------
        str
            Raw reviewer response text.
        """
        return self.client.complete(
            _load_prompt("answer_reviewer"),
            self._review_context(prompt, answer),
        )

    def _rejected(self, review: dict) -> bool:
        """Return whether a review rejects the answer.

        Parameters
        ----------
        review : dict
            Decoded review.

        Returns
        -------
        bool
            ``True`` when approval is explicitly false.
        """
        return review.get("approved") is False

    def _review_context(self, prompt: str, answer: str) -> str:
        """Build the reviewer payload from the answer and tool evidence.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft final answer.

        Returns
        -------
        str
            JSON review context.
        """
        evidence = _tool_evidence(self.messages)
        return json.dumps(
            {
                "question": prompt,
                "answer": answer,
                "tool_evidence": evidence,
            }
        )

    def steer(self, prompt: str) -> None:
        """Queue a message to guide the next agent turn.

        Parameters
        ----------
        prompt : str
            Steering instruction.

        Returns
        -------
        None
            The instruction is queued.
        """
        self.steering.append(prompt)

    def queue_follow_up(self, prompt: str) -> None:
        """Queue a prompt after the current run completes.

        Parameters
        ----------
        prompt : str
            Follow-up instruction.

        Returns
        -------
        None
            The instruction is queued.
        """
        self.follow_up.append(prompt)

    def compact(self, keep: int = 20) -> list[dict[str, Any]]:
        """Compact the active session context.

        Parameters
        ----------
        keep : int
            Number of newest messages to retain.

        Returns
        -------
        list[dict[str, Any]]
            Discarded messages.
        """
        old = self.messages
        self._compact_messages(keep)
        return [item for item in old if item not in self.messages]

    def trim_context(self, keep: int = 8) -> None:
        """Keep only the system prompt and newest messages.

        Parameters
        ----------
        keep : int
            Number of newest messages to retain.

        Returns
        -------
        None
            Older messages are discarded.
        """
        self._compact_messages(keep)

    def _maybe_compact(self) -> None:
        """Compact the context when it exceeds the configured budget.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Older messages may be discarded.
        """
        limit = _int_env("HARNESS_CONTEXT_CHARS", _CONTEXT_CHARS)
        if _message_chars(self.messages) <= limit:
            return
        keep = _int_env("HARNESS_CONTEXT_KEEP", _CONTEXT_KEEP)
        self._compact_messages(keep)

    def _compact_messages(self, keep: int) -> None:
        """Retain the system prompt and the newest complete messages.

        Parameters
        ----------
        keep : int
            Number of newest messages to retain.

        Returns
        -------
        None
            Older messages are discarded.
        """
        if keep <= 0 or len(self.messages) <= keep:
            return
        head = self.messages[:1]
        tail = _complete_tail(self.messages[-keep:])
        self._replace(head + tail)

    def _replace(self, messages: list[dict[str, Any]]) -> None:
        """Replace the conversation and mirror it to the session.

        Parameters
        ----------
        messages : list of dict[str, Any]
            New conversation messages.

        Returns
        -------
        None
            The conversation is replaced.
        """
        self.messages = messages
        if self.session:
            self.session.messages = messages[:]

    def _loop(self) -> str:
        """Process model turns until completion.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Final response or turn-limit message.
        """
        for _ in range(self.max_turns):
            self._maybe_compact()
            message = self._message()
            if not message.get("tool_calls"):
                return str(message.get("content", ""))
            self._execute_calls(message["tool_calls"])
        return self._finalize()

    def _finalize(self) -> str:
        """Request a final answer without tools after the turn limit.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Final assistant text, or a fallback message.
        """
        self._append(_turn_limit_message())
        response = self.client.chat(self.messages, [])
        message = response["choices"][0]["message"]
        self._append(message)
        return str(
            message.get("content")
            or "Agent stopped after reaching the turn limit."
        )

    def _message(self) -> dict[str, Any]:
        """Request and append one assistant message.

        Parameters
        ----------
        None

        Returns
        -------
        dict[str, Any]
            Assistant message.
        """
        self._inject_steering()
        response = self.client.chat(self.messages, self.tools.schema())
        message = response["choices"][0]["message"]
        _repair_tool_calls(message)
        self._append(message)
        return message

    def _inject_steering(self) -> None:
        """Append queued steering messages before a model call.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Queued steering messages are consumed.
        """
        while self.steering:
            self._append({"role": "user", "content": self.steering.pop(0)})

    def _append(self, message: dict[str, Any]) -> None:
        """Append a message to memory and an optional session.

        Parameters
        ----------
        message : dict[str, Any]
            Message to append.

        Returns
        -------
        None
            Message state is updated.
        """
        self.messages.append(message)
        if self.session:
            self.session.append(message)

    def _execute_calls(self, calls: list[dict[str, Any]]) -> None:
        """Execute tool calls and append their results.

        Parameters
        ----------
        calls : list[dict[str, Any]]
            Model tool calls.

        Returns
        -------
        None
            Tool results are appended to the conversation.
        """
        for call in calls:
            self._append(self._tool_result(call))

    def _tool_result(self, call: dict[str, Any]) -> dict[str, Any]:
        """Execute one tool call safely.

        Parameters
        ----------
        call : dict[str, Any]
            OpenAI-compatible tool call.

        Returns
        -------
        dict[str, Any]
            Tool result message.
        """
        function = call["function"]
        arguments, content = self._run_tool(function)
        self._notify(function["name"], arguments, content)
        return {"role": "tool", "tool_call_id": call["id"], "content": content}

    def _run_tool(self, function: dict[str, Any]) -> tuple:
        """Execute one tool call and return its arguments and output.

        Parameters
        ----------
        function : dict[str, Any]
            Tool-call function payload.

        Returns
        -------
        tuple
            Parsed arguments and the tool output string.
        """
        arguments: dict[str, Any] = {}
        try:
            arguments = json.loads(function.get("arguments", "{}"))
            content = self.tools.execute(function["name"], arguments)
        except (ToolError, json.JSONDecodeError, KeyError) as exc:
            content = json.dumps({"error": str(exc)})
        return arguments, content

    def _notify(self, name: str, arguments: dict, content: str) -> None:
        """Report one tool result to the observer.

        Parameters
        ----------
        name : str
            Tool name.

        arguments : dict
            Tool arguments.

        content : str
            Tool result content.

        Returns
        -------
        None
            The observer is called when configured.
        """
        if self.observer is not None:
            self.observer(name, arguments, content)


def _turn_limit_message() -> dict[str, str]:
    """Build the system message that ends tool use.

    Parameters
    ----------
    None

    Returns
    -------
    dict[str, str]
        System message requesting a final answer.
    """
    return {
        "role": "system",
        "content": (
            "Turn limit reached. Answer now using the information "
            "already gathered. Do not call tools."
        ),
    }


def _repair_tool_calls(message: dict[str, Any]) -> None:
    """Replace unparseable tool-call arguments with an empty object.

    Parameters
    ----------
    message : dict[str, Any]
        Assistant message repaired in place.

    Returns
    -------
    None
        Invalid argument strings become ``{}``.
    """
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        try:
            json.loads(function.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            function["arguments"] = "{}"


def _system_prompt() -> str:
    """Build the combined interactive system prompt.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Agent prompt followed by the coding standards.
    """
    return _load_prompt("agent") + "\n\n" + _load_prompt("coding_standards")


def _tool_evidence(messages: list[dict[str, Any]]) -> list[str]:
    """Collect the newest tool-result content for the reviewer.

    Parameters
    ----------
    messages : list of dict[str, Any]
        Conversation messages.

    Returns
    -------
    list of str
        Up to eight trailing tool results, each truncated.
    """
    evidence = [
        str(message.get("content", ""))[-500:]
        for message in messages
        if message.get("role") == "tool"
    ]
    return evidence[-8:]


def _complete_tail(tail: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop leading tool results from a retained tail.

    Parameters
    ----------
    tail : list of dict[str, Any]
        Newest messages to retain.

    Returns
    -------
    list of dict[str, Any]
        Tail without leading tool results.
    """
    index = 0
    while index < len(tail) and tail[index].get("role") == "tool":
        index += 1
    return tail[index:]


def _copy_messages(messages: list[dict]) -> list[dict]:
    """Return a shallow copy of each message mapping.

    Parameters
    ----------
    messages : list[dict]
        Conversation messages.

    Returns
    -------
    list[dict]
        Copied messages.
    """
    return [dict(item) for item in messages]


def _adversarial_drafts() -> int:
    """Return the configured draft count.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Number of drafts, zero when adversarial mode is off.
    """
    raw = os.getenv("HARNESS_ADVERSARIAL_DRAFTS", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _draft_context(prompt: str, drafts: list[str]) -> str:
    """Build the adjudicator payload for draft answers.

    Parameters
    ----------
    prompt : str
        User task.

    drafts : list[str]
        Candidate final answers.

    Returns
    -------
    str
        JSON adjudicator context.
    """
    return json.dumps({"question": prompt, "drafts": drafts})


def _chosen_draft(raw: str, drafts: list[str]) -> str:
    """Decode the chosen draft index.

    Parameters
    ----------
    raw : str
        Adjudicator response.

    drafts : list[str]
        Candidate final answers.

    Returns
    -------
    str
        Chosen draft, defaulting to the first.
    """
    try:
        value = json_value(raw)
        index = int(value.get("selected_index", 0))
    except (ValueError, TypeError, AttributeError):
        return drafts[0]
    return drafts[index] if 0 <= index < len(drafts) else drafts[0]


def _answer_tests_enabled() -> bool:
    """Return whether answer-time reviewer tests are enabled.

    Parameters
    ----------
    None

    Returns
    -------
    bool
        Whether ``HARNESS_ANSWER_TESTS`` enables verification.
    """
    value = os.getenv("HARNESS_ANSWER_TESTS", "0").strip().lower()
    return value in ("1", "true", "yes", "on")


def _workspace_context(prompt: str, answer: str, root: Path) -> str:
    """Build a reviewer context from a workspace snapshot.

    Parameters
    ----------
    prompt : str
        User task.

    answer : str
        Draft answer.

    root : pathlib.Path
        Workspace root.

    Returns
    -------
    str
        JSON context with file contents.
    """
    return json.dumps(
        {
            "task": prompt,
            "answer": answer,
            "files": _workspace_files(root),
        }
    )


def _workspace_files(root: Path) -> dict[str, str]:
    """Read workspace Python files for the reviewer.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    dict
        Relative path to source text for up to twenty files.
    """
    files = {}
    for path in sorted(root.rglob("*.py")):
        relative = str(path.relative_to(root))
        if len(files) < 20 and "__pycache__" not in relative:
            files[relative] = path.read_text(encoding="utf-8")[:4000]
    return files


def _test_sources(raw: str) -> list[str]:
    """Extract reviewer test sources from a response.

    Parameters
    ----------
    raw : str
        Reviewer response.

    Returns
    -------
    list[str]
        Non-empty unittest sources.
    """
    try:
        value = json_value(raw)
    except ValueError:
        return []
    if not isinstance(value, dict):
        return []
    return _clean_tests(value.get("tests"))


def _clean_tests(tests) -> list[str]:
    """Return non-empty test sources from a decoded field.

    Parameters
    ----------
    tests : object
        Decoded ``tests`` field.

    Returns
    -------
    list[str]
        Non-empty unittest sources.
    """
    if not isinstance(tests, list):
        return []
    return [item for item in tests if isinstance(item, str) and item.strip()]


def _repair_message(output: str) -> dict[str, str]:
    """Build the system message that requests a repair.

    Parameters
    ----------
    output : str
        Failing test output.

    Returns
    -------
    dict[str, str]
        System message with the failure details.
    """
    detail = output[-2000:]
    return {
        "role": "system",
        "content": "Reviewer tests failed. Fix the workspace, then finish.\n"
        + detail,
    }


def _snapshot(parent: Path, root: Path) -> Path:
    """Copy a workspace into a snapshot directory.

    Parameters
    ----------
    parent : pathlib.Path
        Temporary directory.

    root : pathlib.Path
        Workspace root.

    Returns
    -------
    pathlib.Path
        Snapshot workspace path.
    """
    snapshot = parent / "workspace"
    shutil.copytree(root, snapshot)
    return snapshot


def _restore_workspace(root: Path, snapshot: Path) -> None:
    """Restore a workspace from a snapshot.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    snapshot : pathlib.Path
        Snapshot directory.

    Returns
    -------
    None
        The workspace contents are replaced.
    """
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    shutil.copytree(snapshot, root, dirs_exist_ok=True)
