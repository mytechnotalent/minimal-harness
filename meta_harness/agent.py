"""Pi-like stateful tool-calling agent runtime."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ._json_util import json_value
from .deliverables import deliverable_issues
from .invariants import relevant_invariants
from .ledger import ledger_issues
from .ledger import limit_issues
from .ledger import needs_ledger
from .openrouter import OpenRouterClient
from .profiles import profile_for
from .prompts import load as _load_prompt
from .requirements import needs_requirements
from .requirements import requirement_issues
from .session import Session
from .sandbox import TestSandbox
from .task_evaluator import run_workspace_tests
from .tools import ToolError
from .tools import ToolRegistry
from .tools import _compact_test_output

_CONTEXT_CHARS = 250000
_EDIT_TOOLS = ("edit", "write", "patch")
_NUDGE_TOOLS = ("edit", "write", "patch", "read", "grep", "glob")
_CONTEXT_KEEP = 24
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
_ARTIFACT_CHARS = 6000
_ARTIFACT_FILES = 6
_REVIEW_MODES = ("verifiable", "survey", "advisory")
_MUTATING_TOOLS = _EDIT_TOOLS + ("bash",)
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "node_modules",
    "runs",
    "build",
    "dist",
}


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


def _repo_env() -> bool:
    """Return whether repository mode is configured in environment.

    Parameters
    ----------
    None

    Returns
    -------
    bool
        ``True`` when repository mode is enabled.
    """
    value = os.getenv("HARNESS_REPO", "0").strip().lower()
    return value in ("1", "true", "yes", "on")


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
        web_enabled: bool = True,
        lean: bool = False,
        repo: bool = False,
        system_prompt: str | None = None,
        tools: ToolRegistry | None = None,
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

        web_enabled : bool
            Advertise web and browser tools.

        lean : bool
            Use the short repo-editing prompt.
        repo : bool
            Use the existing-repository prompt.

        system_prompt : str or None
            Optional full system prompt override.
        tools : ToolRegistry or None
            Optional preconfigured tool registry.

        Returns
        -------
        None
            This initializer configures the agent.
        """
        self.observer, self.system_prompt = observer, system_prompt
        self.lean = lean
        self.repo = repo or _repo_env()
        self.client = client or OpenRouterClient()
        self.tools = tools or ToolRegistry(root, web_enabled=web_enabled)
        self.max_turns = max_turns
        self.session = session
        self._init_state(session)

    def _init_state(self, session: Session | None) -> None:
        """Initialize messages and per-run task state.

        Parameters
        ----------
        session : Session or None
            Optional persisted session.

        Returns
        -------
        None
            Messages and run state are initialized.
        """
        self.messages = self._initial_messages(session)
        self._init_task_state()

    def _init_task_state(self) -> None:
        """Initialize per-run task state.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Queue and mutation fields are initialized.
        """
        self.steering: list[str] = []
        self.follow_up: list[str] = []
        self._mutated = False
        self._nudged = False
        self._workspace_before: dict[str, tuple[int, int]] | None = None
        self._init_execution_state()
        self.review_events: list[dict[str, Any]] = []

    def _init_execution_state(self) -> None:
        """Initialize the execution trace and task boundary.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Trace, task id, and task start are initialized.
        """
        self._trace: list[dict[str, Any]] = []
        self._task_id = ""
        self._task_start = 0

    def _begin_run(self, prompt: str) -> None:
        """Reset run state and append the user turn.

        Parameters
        ----------
        prompt : str
            User task.

        Returns
        -------
        None
            The conversation is updated.
        """
        self._mutated = False
        self._workspace_before = None
        self._trace = []
        self._task_id = uuid.uuid4().hex[:8]
        self.review_events = []
        self._task_start = len(self.messages)
        self._append({"role": "user", "content": prompt})
        self._trim_system(prompt)

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
        prompt = self.system_prompt or _system_prompt(self.lean, self.repo)
        if messages and messages[0].get("role") == "system":
            messages[0] = {"role": "system", "content": prompt}
            return messages
        return [{"role": "system", "content": prompt}] + messages

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
        self._begin_run(prompt)
        answer = self._loop()
        answer = self._auto_verify(prompt, answer)
        answer = self._verified_answer(prompt, answer)
        return self._review_final(prompt, answer)

    def _auto_verify(self, prompt: str, answer: str) -> str:
        """Run project tests and repair bounded failures.

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
        if not _auto_verify_enabled():
            return answer
        passed, output = self._project_tests()
        if passed:
            return answer
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = _snapshot(Path(temporary), self.tools.root)
            return self._verify_loop(answer, snapshot, output)

    def _verify_loop(self, answer: str, snapshot: Path, output: str) -> str:
        """Attempt bounded project-test repairs.

        Parameters
        ----------
        answer : str
            Original answer.
        snapshot : pathlib.Path
            Workspace snapshot.
        output : str
            Initial failing test output.

        Returns
        -------
        str
            Repaired answer when tests pass, otherwise the original.
        """
        for _ in range(_verify_attempts()):
            self._append(_verify_message(output))
            repaired = self._loop()
            passed, output = self._project_tests()
            if passed:
                return repaired
        _restore_workspace(self.tools.root, snapshot)
        return answer

    def _project_tests(self) -> tuple[bool, str]:
        """Run the project's own tests.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[bool, str]
            Whether tests passed, and combined output.
        """
        command = _test_command(self.tools.root)
        if os.getenv("HARNESS_SANDBOX_TESTS", "0").strip() == "1":
            return TestSandbox().run(self.tools.root, command)
        return _run_local_tests(self.tools.root, command)

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
            return self._repair_loop(tests, answer, snapshot, output)

    def _repair_loop(self, tests, answer, snapshot, output) -> str:
        """Attempt bounded repairs until tests pass or output repeats.

        Parameters
        ----------
        tests : list[str]
            Reviewer-generated unittest sources.

        answer : str
            Original answer.

        snapshot : pathlib.Path
            Workspace snapshot.

        output : str
            Initial failing test output.

        Returns
        -------
        str
            Repaired answer when tests pass, otherwise the original.
        """
        for _ in range(_repair_attempts()):
            repaired, output = self._repair_step(tests, output)
            if repaired is not None:
                return repaired
        _restore_workspace(self.tools.root, snapshot)
        return answer

    def _repair_step(self, tests, output) -> tuple:
        """Run one bounded repair attempt and retest the workspace.

        Parameters
        ----------
        tests : list[str]
            Reviewer-generated unittest sources.
        output : str
            Failing test output.

        Returns
        -------
        tuple
            Repaired answer or ``None``, and the latest test output.
        """
        self._append(_repair_message(output))
        repaired = self._loop()
        passed, output = run_workspace_tests(self.tools.root, tests)
        return (repaired if passed else None), output

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
        self._begin_run(prompt)
        base = _copy_messages(self.messages)
        drafts = self._drafts(base)
        best = self._pick_draft(prompt, drafts)
        self.messages = _copy_messages(base)
        self._append({"role": "assistant", "content": best})
        return self._review_final(prompt, best)

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
        if self.lean or self.repo:
            return
        self._trim_standards(prompt)

    def _trim_standards(self, prompt: str) -> None:
        """Apply the coding-standards policy.

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

    def _review_final(self, prompt: str, answer: str) -> str:
        """Run the ledger check and the answer review.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.

        Returns
        -------
        str
            Reviewed answer.
        """
        if not self._review_enabled(answer):
            self._record_review("skipped", "disabled")
            return answer
        if _is_turn_limit(answer, self.max_turns):
            self._record_review("skipped", "turn_limit")
            return answer
        return self._reviewed(prompt, answer)

    def _reviewed(self, prompt: str, answer: str) -> str:
        """Run deterministic checks and the adversarial answer review.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.

        Returns
        -------
        str
            Reviewed answer.
        """
        self._mark_trace_usage(answer)
        verification = self._verify_ledger(prompt, answer)
        invariants = self._invariant_review(prompt, answer)
        requirements = self._requirement_review(prompt, answer)
        return self._review_answer(
            prompt, answer, verification, invariants, requirements
        )

    def _review_answer(
        self,
        prompt: str,
        answer: str,
        verification: dict | None = None,
        invariants: dict | None = None,
        requirements: dict | None = None,
    ) -> str:
        """Adversarially review and possibly revise a final answer.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft final answer.
        verification : dict or None
            Deterministic ledger findings.
        invariants : dict or None
            Technical invariant findings.
        requirements : dict or None
            Requirement-state findings.

        Returns
        -------
        str
            Approved answer or a revised answer.
        """
        if not self._review_enabled(answer):
            self._record_review("skipped", "disabled")
            return answer
        return self._apply_verdict(
            prompt, answer, verification, invariants, requirements
        )

    def _apply_verdict(
        self,
        prompt: str,
        answer: str,
        verification: dict | None,
        invariants: dict | None,
        requirements: dict | None,
    ) -> str:
        """Apply the adversarial review verdict to an answer.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft final answer.
        verification : dict or None
            Deterministic ledger findings.
        invariants : dict or None
            Technical invariant findings.
        requirements : dict or None
            Requirement-state findings.

        Returns
        -------
        str
            Approved answer or a revised answer.
        """
        review = self._answer_review(
            prompt, answer, verification, invariants, requirements
        )
        if not review:
            return answer
        return self._apply_review(answer, review)

    def _ledger_enabled(self, prompt: str, answer: str) -> bool:
        """Return whether the ledger check should run.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.

        Returns
        -------
        bool
            ``True`` when configured and the task needs numeric checks.
        """
        mode = _ledger_mode()
        if not hasattr(self.client, "complete"):
            return False
        if mode == "auto":
            return needs_ledger(prompt, answer)
        return mode == "on"

    def _verify_ledger(self, prompt: str, answer: str) -> dict | None:
        """Extract and check a numeric ledger for one answer.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.

        Returns
        -------
        dict or None
            Ledger with deterministic issues, or ``None`` when skipped.
        """
        if not self._ledger_enabled(prompt, answer):
            return None
        ledger = self._ledger_data(prompt, answer)
        issues = _verification_issues(prompt, answer, ledger)
        if ledger is None and not issues:
            return None
        self._record_ledger(issues)
        return {**(ledger or {}), "issues": issues}

    def _ledger_data(self, prompt: str, answer: str) -> dict | None:
        """Request and decode the ledger for one answer.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.

        Returns
        -------
        dict or None
            Decoded ledger, or ``None`` when unavailable.
        """
        raw = self._ledger_raw(prompt, answer)
        if not raw:
            return None
        value = _ledger_value(raw)
        if value is None:
            self._record_review("ledger", "invalid")
            return None
        return _applicable_ledger(value, self._record_review)

    def _ledger_raw(self, prompt: str, answer: str) -> str:
        """Request the raw ledger response.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.

        Returns
        -------
        str
            Raw ledger response, or an empty string on failure.
        """
        context = json.dumps({"question": prompt, "answer": answer})
        try:
            return self._review_with_timeout(
                _load_prompt("verify_ledger"), context
            )
        except Exception as exc:
            self._record_review("ledger", "error", detail=str(exc))
            return ""

    def _record_ledger(self, issues: list[str]) -> None:
        """Record one ledger decision.

        Parameters
        ----------
        issues : list of str
            Deterministic issues.

        Returns
        -------
        None
            The event is stored and optionally logged.
        """
        reason = "mismatch" if issues else "ok"
        self._record_review("ledger", reason, issues=issues)

    def _requirement_enabled(self, prompt: str) -> bool:
        """Return whether requirement extraction should run.

        Parameters
        ----------
        prompt : str
            Current user question.

        Returns
        -------
        bool
            ``True`` when configured and the task needs it.
        """
        mode = _requirement_mode()
        if mode == "off" or not hasattr(self.client, "complete"):
            return False
        if mode == "on":
            return True
        return needs_requirements(prompt, self._requirement_history())

    def _requirement_history(self) -> list[str]:
        """Return prior user requests for requirement extraction.

        Parameters
        ----------
        None

        Returns
        -------
        list of str
            Up to eight earlier requests, each bounded.
        """
        history = [
            str(message.get("content") or "")[:2000]
            for message in self.messages[: self._task_start]
            if message.get("role") == "user"
        ]
        return history[-8:]

    def _requirement_review(self, prompt: str, answer: str) -> dict | None:
        """Extract requirement states and contradiction issues.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.

        Returns
        -------
        dict or None
            Requirement findings, or ``None`` when skipped.
        """
        if not self._requirement_enabled(prompt):
            return None
        history = self._requirement_history()
        return self._requirement_result(prompt, answer, history)

    def _requirement_result(
        self, prompt: str, answer: str, history: list[str]
    ) -> dict | None:
        """Return requirement findings for one answer.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.
        history : list of str
            Earlier user requests.

        Returns
        -------
        dict or None
            Requirement findings, or ``None`` when unavailable.
        """
        ledger = self._requirement_data(prompt, answer, history)
        if ledger is None:
            return None
        issues = requirement_issues(ledger)
        self._record_requirements(issues)
        return {**ledger, "issues": issues}

    def _requirement_data(
        self, prompt: str, answer: str, history: list[str]
    ) -> dict | None:
        """Request and decode the requirement extraction.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.
        history : list of str
            Earlier user requests.

        Returns
        -------
        dict or None
            Decoded ledger, or ``None`` when unavailable.
        """
        raw = self._requirement_raw(prompt, answer, history)
        if not raw:
            return None
        return self._requirement_decoded(raw)

    def _requirement_decoded(self, raw: str) -> dict | None:
        """Decode and screen a requirement extraction.

        Parameters
        ----------
        raw : str
            Raw extractor response.

        Returns
        -------
        dict or None
            Decoded ledger, or ``None`` when unavailable.
        """
        value = _ledger_value(raw)
        if value is None:
            self._record_review("requirements", "invalid")
            return None
        if value.get("applies") is False:
            self._record_review("requirements", "not_applicable")
            return None
        return value

    def _requirement_raw(
        self, prompt: str, answer: str, history: list[str]
    ) -> str:
        """Request the raw requirement extraction.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.
        history : list of str
            Earlier user requests.

        Returns
        -------
        str
            Raw extraction response, or an empty string on failure.
        """
        context = _requirement_context(history, prompt, answer)
        try:
            return self._review_with_timeout(
                _load_prompt("requirements_reviewer"), context
            )
        except Exception as exc:
            self._record_review("requirements", "error", detail=str(exc))
            return ""

    def _record_requirements(self, issues: list[str]) -> None:
        """Record one requirement decision.

        Parameters
        ----------
        issues : list of str
            Deterministic issues.

        Returns
        -------
        None
            The event is stored and optionally logged.
        """
        reason = "conflict" if issues else "ok"
        self._record_review("requirements", reason, issues=issues)

    def _invariant_enabled(self) -> bool:
        """Return whether invariant checks are configured.

        Parameters
        ----------
        None

        Returns
        -------
        bool
            ``True`` when the client supports completion and the mode is on.
        """
        mode = _invariant_mode()
        if mode == "off" or not hasattr(self.client, "complete"):
            return False
        return mode in ("auto", "on")

    def _invariant_review(self, prompt: str, answer: str) -> dict | None:
        """Check the answer against matching technical invariants.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.

        Returns
        -------
        dict or None
            Matching rules and violations, or ``None`` when skipped.
        """
        rules = relevant_invariants(prompt, answer)
        if not rules or not self._invariant_enabled():
            return None
        return self._invariant_findings(prompt, answer, rules)

    def _invariant_findings(
        self, prompt: str, answer: str, rules: list[str]
    ) -> dict | None:
        """Return the invariant findings for one answer.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.
        rules : list of str
            Selected invariants.

        Returns
        -------
        dict or None
            Matching rules and violations, or ``None`` when unavailable.
        """
        data = self._invariant_data(prompt, answer, rules)
        if data is None:
            return None
        violations = _violations(data)
        self._record_invariant(violations)
        return {"rules": rules, "violations": violations}

    def _invariant_data(
        self, prompt: str, answer: str, rules: list[str]
    ) -> dict | None:
        """Request and decode the invariant verdict.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.
        rules : list of str
            Selected invariants.

        Returns
        -------
        dict or None
            Decoded verdict, or ``None`` when unavailable.
        """
        raw = self._invariant_raw(prompt, answer, rules)
        if not raw:
            return None
        value = _invariant_value(raw)
        if value is None:
            self._record_review("invariant", "invalid")
        return value

    def _invariant_raw(
        self, prompt: str, answer: str, rules: list[str]
    ) -> str:
        """Request the raw invariant verdict.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.
        rules : list of str
            Selected invariants.

        Returns
        -------
        str
            Raw verdict, or an empty string on failure.
        """
        context = _invariant_context(prompt, answer, rules)
        try:
            return self._review_with_timeout(
                _load_prompt("technical_reviewer"), context
            )
        except Exception as exc:
            self._record_review("invariant", "error", detail=str(exc))
            return ""

    def _record_invariant(self, violations: list[str]) -> None:
        """Record one invariant decision.

        Parameters
        ----------
        violations : list of str
            Confirmed violations.

        Returns
        -------
        None
            The event is stored and optionally logged.
        """
        reason = "violation" if violations else "ok"
        self._record_review("invariant", reason, issues=violations)

    def _apply_review(self, answer: str, review: dict) -> str:
        """Apply an engaged review verdict.

        Parameters
        ----------
        answer : str
            Draft answer.
        review : dict
            Decoded reviewer response.

        Returns
        -------
        str
            Approved, caveated, or revised answer.
        """
        mode = _review_mode(review)
        blocking = _blocking_review(review, mode)
        revised = review.get("revised_answer")
        if _allow_revision(mode, answer, revised, blocking):
            return self._revised_review(answer, revised, mode)
        return self._kept_review(answer, mode, blocking)

    def _revised_review(self, original: str, revised: str, mode: str) -> str:
        """Record and return a reviewer replacement.

        Parameters
        ----------
        original : str
            Draft answer before review.
        revised : str
            Replacement answer.
        mode : str
            Review mode.

        Returns
        -------
        str
            Replacement answer text.
        """
        text = str(revised).strip()
        self._record_review(
            "engaged", "revised", mode=mode, original=original, revised=text
        )
        return text

    def _kept_review(self, answer: str, mode: str, blocking: bool) -> str:
        """Record and return the original answer.

        Parameters
        ----------
        answer : str
            Draft answer.
        mode : str
            Review mode.
        blocking : bool
            Whether a concrete defect was found.

        Returns
        -------
        str
            Original answer text.
        """
        reason = "rejected" if blocking else "approved"
        self._record_review("engaged", reason, mode=mode)
        return answer

    def _record_review(self, event: str, reason: str, **extra: Any) -> None:
        """Record one review engagement event.

        Parameters
        ----------
        event : str
            Short event label, such as ``engaged`` or ``ledger``.
        reason : str
            Short outcome label.
        **extra : Any
            Additional event fields.

        Returns
        -------
        None
            The event is stored and optionally logged.
        """
        record = {
            "event": event,
            "reason": reason,
            "mutated": self._mutated,
            **extra,
        }
        self.review_events.append(record)
        _append_review_log(record)

    def _review_enabled(self, answer: str = "") -> bool:
        """Return whether answer review is enabled.

        Parameters
        ----------
        answer : str
            Draft answer used by ``auto`` mode and the code-bearing skip.

        Returns
        -------
        bool
            ``True`` when configured and the client supports completion.
        """
        mode = os.getenv("HARNESS_ANSWER_REVIEW", "1").strip().lower()
        if not hasattr(self.client, "complete"):
            return False
        if mode in ("0", "false", "no", "off") or _has_code_block(answer):
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

    def _answer_review(
        self,
        prompt: str,
        answer: str,
        verification: dict | None = None,
        invariants: dict | None = None,
        requirements: dict | None = None,
    ) -> dict:
        """Request one structured answer review.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft final answer.
        verification : dict or None
            Deterministic ledger findings.
        invariants : dict or None
            Technical invariant findings.
        requirements : dict or None
            Requirement-state findings.

        Returns
        -------
        dict
            Decoded review, or an empty dict on failure.
        """
        try:
            raw = self._review_raw(
                prompt, answer, verification, invariants, requirements
            )
        except Exception as exc:
            self._record_review("skipped", "error", detail=str(exc))
            return {}
        return self._decoded_review(raw)

    def _decoded_review(self, raw: str) -> dict:
        """Decode a reviewer response into a verdict.

        Parameters
        ----------
        raw : str
            Raw reviewer response text.

        Returns
        -------
        dict
            Decoded verdict, or an empty dict when invalid.
        """
        try:
            value = json_value(raw)
        except ValueError:
            value = None
        if isinstance(value, dict):
            return value
        self._record_review("skipped", "invalid_response")
        return {}

    def _review_raw(
        self,
        prompt: str,
        answer: str,
        verification: dict | None = None,
        invariants: dict | None = None,
        requirements: dict | None = None,
    ) -> str:
        """Request the raw reviewer response.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft final answer.
        verification : dict or None
            Deterministic ledger findings.
        invariants : dict or None
            Technical invariant findings.
        requirements : dict or None
            Requirement-state findings.

        Returns
        -------
        str
            Raw reviewer response text.
        """
        context = self._review_context(
            prompt, answer, verification, invariants, requirements
        )
        return self._review_with_timeout(
            _load_prompt("answer_reviewer"), context
        )

    def _review_with_timeout(self, system: str, user: str) -> str:
        """Run one review call with a bounded wait.

        Parameters
        ----------
        system : str
            Review instruction.
        user : str
            Review payload.

        Returns
        -------
        str
            Reviewer response text.
        """
        saved: list[Any] = []
        worker = self._review_worker(system, user, saved)
        worker.start()
        worker.join(self._review_timeout())
        if not saved:
            raise TimeoutError("answer review timed out")
        return _review_response(saved[0])

    def _review_worker(
        self, system: str, user: str, saved: list[Any]
    ) -> threading.Thread:
        """Build the reviewer worker thread.

        Parameters
        ----------
        system : str
            Review instruction.
        user : str
            Review payload.
        saved : list of Any
            Collector for the response or exception.

        Returns
        -------
        threading.Thread
            Daemon worker ready to start.
        """
        return threading.Thread(
            target=lambda: _review_call(self.client, system, user, saved),
            daemon=True,
        )

    def _review_timeout(self) -> float:
        """Return the review call timeout in seconds.

        Parameters
        ----------
        None

        Returns
        -------
        float
            Configured timeout.
        """
        return float(os.getenv("HARNESS_REVIEW_TIMEOUT", "30"))

    def _review_context(
        self,
        prompt: str,
        answer: str,
        verification: dict | None = None,
        invariants: dict | None = None,
        requirements: dict | None = None,
    ) -> str:
        """Build the reviewer payload from the answer and tool evidence.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft final answer.
        verification : dict or None
            Deterministic ledger findings.
        invariants : dict or None
            Technical invariant findings.
        requirements : dict or None
            Requirement-state findings.

        Returns
        -------
        str
            JSON review context.
        """
        payload = self._review_payload(
            prompt, answer, verification, invariants, requirements
        )
        return json.dumps(payload)

    def _review_payload(
        self,
        prompt: str,
        answer: str,
        verification: dict | None = None,
        invariants: dict | None = None,
        requirements: dict | None = None,
    ) -> dict[str, Any]:
        """Build the reviewer context as a mapping.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft final answer.
        verification : dict or None
            Deterministic ledger findings.
        invariants : dict or None
            Technical invariant findings.
        requirements : dict or None
            Requirement-state findings.

        Returns
        -------
        dict[str, Any]
            Question, answer, evidence, artifacts, and checks.
        """
        payload = _base_payload(prompt, answer, self.messages, self._trace)
        payload["deliverables"] = self._deliverable_context(prompt, answer)
        return self._complete_context(
            payload, verification, invariants, requirements
        )

    def _complete_context(
        self,
        payload: dict[str, Any],
        verification: dict | None,
        invariants: dict | None,
        requirements: dict | None,
    ) -> dict[str, Any]:
        """Attach checks and task boundary to a reviewer payload.

        Parameters
        ----------
        payload : dict[str, Any]
            Base reviewer payload.
        verification : dict or None
            Deterministic ledger findings.
        invariants : dict or None
            Technical invariant findings.
        requirements : dict or None
            Requirement-state findings.

        Returns
        -------
        dict[str, Any]
            Completed reviewer context.
        """
        if verification:
            payload["verification"] = verification
        if invariants:
            payload["invariants"] = invariants
        if requirements:
            payload["requirements"] = requirements
        payload["task"] = self._task_context()
        return self._attach_artifacts(payload)

    def _task_messages(self) -> list[dict[str, Any]]:
        """Return messages from the current task only.

        Parameters
        ----------
        None

        Returns
        -------
        list of dict[str, Any]
            Messages at or after the task start.
        """
        return self.messages[self._task_start :]

    def _attach_artifacts(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Attach current-task artifacts to a reviewer payload.

        Parameters
        ----------
        payload : dict[str, Any]
            Reviewer payload.

        Returns
        -------
        dict[str, Any]
            Payload with current-task artifacts.
        """
        recent = self._task_messages()
        return _with_artifacts(
            payload, recent, self.tools.root, self._workspace_before
        )

    def _task_context(self) -> dict[str, Any]:
        """Return the current task boundary and changed files.

        Parameters
        ----------
        None

        Returns
        -------
        dict[str, Any]
            Workspace, prior requests, and current-run files.
        """
        prior = _prior_requests(self.messages, self._task_start)
        return {
            "workspace": str(self.tools.root),
            "prior_requests": prior,
            "changed_files": self._task_files(),
        }

    def _deliverable_context(self, prompt: str, answer: str) -> dict:
        """Return current-task files and deliverable issues.

        Parameters
        ----------
        prompt : str
            User question.
        answer : str
            Draft answer.

        Returns
        -------
        dict
            Changed files and deterministic deliverable issues.
        """
        changed = self._task_files()
        issues = deliverable_issues(prompt, answer, changed, self._trace)
        return {"changed_files": changed, "issues": issues}

    def _task_files(self) -> list[str]:
        """Return paths changed during the current task only.

        Parameters
        ----------
        None

        Returns
        -------
        list of str
            Current-run workspace paths.
        """
        paths = _changed_paths(self._task_messages())
        return _task_changed(paths, self.tools.root, self._workspace_before)

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
        limit = self._context_limit()
        if _message_chars(self.messages) <= limit:
            return
        keep = _int_env("HARNESS_CONTEXT_KEEP", _CONTEXT_KEEP)
        self._compact_messages(keep)

    def _context_limit(self) -> int:
        """Return the effective context character limit.

        Parameters
        ----------
        None

        Returns
        -------
        int
            Character budget from environment or model profile.
        """
        default = _profile_context_chars(self.client)
        return _int_env("HARNESS_CONTEXT_CHARS", default)

    def _compact_messages(self, keep: int) -> None:
        """Retain pinned messages and the newest complete turns.

        Parameters
        ----------
        keep : int
            Number of newest messages to retain.

        Returns
        -------
        None
            Older messages are discarded.
        """
        head = _head_messages(self.messages, keep)
        if keep <= 0 or len(self.messages) <= max(keep, len(head)):
            return
        start = max(len(head), len(self.messages) - keep)
        tail = _complete_tail(self.messages[start:])
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
        for turn in range(self.max_turns):
            self._maybe_compact()
            self._maybe_nudge(turn)
            message = self._message(turn)
            if not message.get("tool_calls"):
                return _final_text(message)
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
        for _ in range(2):
            message = self._final_attempt()
            if not message.get("tool_calls"):
                text = _final_text(message)
                return text or _turn_limit_text(self.max_turns)
            self._execute_calls(message["tool_calls"])
        return _turn_limit_text(self.max_turns)

    def _final_attempt(self) -> dict[str, Any]:
        """Request, append, and return one final assistant message.

        Parameters
        ----------
        None

        Returns
        -------
        dict[str, Any]
            Final assistant message.
        """
        message = self._final_message()
        self._append(message)
        return message

    def _final_message(self) -> dict[str, Any]:
        """Request one final answer without advertised tools.

        Parameters
        ----------
        None

        Returns
        -------
        dict[str, Any]
            Assistant message with any markup converted to calls.
        """
        response = self.client.chat(self.messages, [])
        message = response["choices"][0]["message"]
        _recover_markup_calls(message, set(self.tools.tools))
        return message

    def _message(self, turn: int = 0) -> dict[str, Any]:
        """Request and append one assistant message.

        Parameters
        ----------
        turn : int
            Zero-based turn index.

        Returns
        -------
        dict[str, Any]
            Assistant message.
        """
        self._inject_steering()
        response = self.client.chat(self.messages, self._tool_schemas(turn))
        message = response["choices"][0]["message"]
        _repair_tool_calls(message)
        _recover_markup_calls(message, set(self.tools.tools))
        self._append(message)
        return message

    def _maybe_nudge(self, turn: int) -> None:
        """Nudge a model that explores without editing files.

        Parameters
        ----------
        turn : int
            Zero-based turn index.

        Returns
        -------
        None
            A nudge is appended once.
        """
        if self._mutated or self._nudged or turn < _nudge_turn():
            return
        self._nudged = True
        self._append(_edit_nudge_message())

    def _tool_schemas(self, turn: int) -> list[dict[str, Any]]:
        """Return the tools advertised for a turn.

        Parameters
        ----------
        turn : int
            Zero-based turn index.

        Returns
        -------
        list[dict[str, Any]]
            Full tools, or edit tools after the nudge.
        """
        if self._mutated or turn < _nudge_turn():
            return self.tools.schema()
        return self.tools.schema(_NUDGE_TOOLS)

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
        name = function.get("name")
        self._prepare_tool(name)
        if self._nudged and not self._mutated:
            if not self._nudge_allowed(function):
                return self._blocked_result(call)
        return self._allowed_result(call, function, name)

    def _prepare_tool(self, name: str) -> None:
        """Mark mutation and capture the workspace before a tool runs.

        Parameters
        ----------
        name : str
            Tool name.

        Returns
        -------
        None
            Mutation state and the pre-run baseline are updated.
        """
        if name in _EDIT_TOOLS:
            self._mutated = True
        if name in _MUTATING_TOOLS and self._workspace_before is None:
            self._workspace_before = _workspace_state(self.tools.root)

    def _nudge_allowed(self, function: dict[str, Any]) -> bool:
        """Return whether a tool may run after the exploration nudge.

        Parameters
        ----------
        function : dict[str, Any]
            Tool-call function payload.

        Returns
        -------
        bool
            ``True`` for inspection, edit, or test commands.
        """
        name = function.get("name")
        if name in _NUDGE_TOOLS:
            return True
        if name != "bash":
            return False
        return _is_test_command(function.get("arguments", ""))

    def _allowed_result(self, call, function, name) -> dict[str, Any]:
        """Execute one allowed tool call.

        Parameters
        ----------
        call : dict[str, Any]
            Tool call.
        function : dict[str, Any]
            Function payload.
        name : str
            Tool name.

        Returns
        -------
        dict[str, Any]
            Tool result message.
        """
        arguments, content, status = self._run_tool(function)
        self._record_trace(name, arguments, content, status)
        self._notify(name, arguments, content)
        return {"role": "tool", "tool_call_id": call["id"], "content": content}

    def _blocked_result(self, call) -> dict[str, Any]:
        """Return an error for non-edit tools after the nudge.

        Parameters
        ----------
        call : dict[str, Any]
            Tool call.

        Returns
        -------
        dict[str, Any]
            Tool result message.
        """
        name = call["function"]["name"]
        content = _blocked_tool_message(name)
        self._record_trace(name, {}, content, "blocked")
        self._notify(name, {}, content)
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
            Parsed arguments, output string, and status label.
        """
        arguments: dict[str, Any] = {}
        try:
            arguments = json.loads(function.get("arguments", "{}"))
            content = self.tools.execute(function["name"], arguments)
            return arguments, content, "ok"
        except (ToolError, json.JSONDecodeError, KeyError) as exc:
            return arguments, json.dumps({"error": str(exc)}), "error"

    def _record_trace(
        self,
        name: str,
        arguments: dict[str, Any],
        content: str,
        status: str,
    ) -> None:
        """Append one auditable tool invocation to the trace.

        Parameters
        ----------
        name : str
            Tool name.
        arguments : dict[str, Any]
            Parsed tool arguments.
        content : str
            Tool output string.
        status : str
            Status label: ok, error, or blocked.

        Returns
        -------
        None
            The trace entry is appended.
        """
        entry = _trace_core(self._task_id, name, arguments, status)
        entry["result"] = _result_head(content)
        entry["result_chars"] = len(content)
        entry["retry_of"] = _retry_of(self._trace, name, entry["arguments"])
        entry["id"] = f"tool-{len(self._trace) + 1}"
        entry["workspace"] = str(self.tools.root)
        self._trace.append(entry)
        _append_trace_record(entry)

    def _mark_trace_usage(self, answer: str) -> None:
        """Mark execution records cited in the final answer.

        Parameters
        ----------
        answer : str
            Final answer text.

        Returns
        -------
        None
            Matching records gain ``used_in_final``.
        """
        for entry in self._trace:
            if _trace_used(entry, answer):
                entry["used_in_final"] = True

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


def _turn_limit_text(limit: int) -> str:
    """Return the fallback text after the turn limit.

    Parameters
    ----------
    limit : int
        Configured turn budget.

    Returns
    -------
    str
        Fallback message naming the limit.
    """
    return f"Agent stopped after reaching the turn limit of {limit} turns."


def _is_turn_limit(answer: str, limit: int) -> bool:
    """Return whether an answer is the turn-limit fallback.

    Parameters
    ----------
    answer : str
        Final answer text.
    limit : int
        Configured turn budget.

    Returns
    -------
    bool
        ``True`` when the answer is the fallback message.
    """
    return answer == _turn_limit_text(limit)


def _blocked_tool_message(name: str) -> str:
    """Return an error that forces an edit after the nudge.

    Parameters
    ----------
    name : str
        Requested tool name.

    Returns
    -------
    str
        JSON error message.
    """
    message = (
        f"{name} is unavailable until you edit a file. "
        "Use edit, write, patch, or read now."
    )
    return json.dumps({"error": message})


def _nudge_turn() -> int:
    """Return the turn threshold for the exploration nudge.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Turn threshold after which the nudge fires.
    """
    return _int_env("HARNESS_NUDGE_TURN", 3)


def _edit_nudge_message() -> dict[str, str]:
    """Build a user message that forces an edit after exploration.

    Parameters
    ----------
    None

    Returns
    -------
    dict[str, str]
        Nudge message.
    """
    content = (
        "You have not modified any file yet. Stop exploring and call the "
        "edit or write tool now. Make the smallest change that addresses "
        "the request, then run one test."
    )
    return {"role": "user", "content": content}


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


_MARKUP_CALL = re.compile(
    r"<tool_call:[^>]+>\s*([A-Za-z0-9_]+)(.*?)</tool_call:[^>]+>",
    re.S,
)
_MARKUP_ARG = re.compile(
    r"<arg_key:[^>]+>(.*?)</arg_key:[^>]+>\s*"
    r"<arg_value:[^>]+>(.*?)</arg_value:[^>]+>",
    re.S,
)
_MARKUP_GROUP = re.compile(r"<tool_calls:[^>]*>.*?</tool_calls:[^>]*>", re.S)
_MARKUP_ONE = re.compile(r"<tool_call:[^>]*>.*?</tool_call:[^>]*>", re.S)


def _recover_markup_calls(message: dict[str, Any], allowed: set) -> None:
    """Convert embedded tool-call markup into real tool calls.

    Parameters
    ----------
    message : dict[str, Any]
        Assistant message repaired in place.
    allowed : set
        Tool names the registry can execute.

    Returns
    -------
    None
        Valid markup becomes ``tool_calls`` and is removed from content.
    """
    content = str(message.get("content") or "")
    calls = _markup_calls(content)
    if message.get("tool_calls") or not _valid_calls(calls, allowed):
        return
    message["tool_calls"] = calls
    message["content"] = _strip_markup(content)


def _markup_calls(content: str) -> list[dict[str, Any]]:
    """Parse tool-call markup into OpenAI-style calls.

    Parameters
    ----------
    content : str
        Assistant text that may contain markup.

    Returns
    -------
    list of dict[str, Any]
        Parsed calls, in source order.
    """
    matches = list(_MARKUP_CALL.finditer(content))
    return [_markup_call(match, index) for index, match in enumerate(matches)]


def _markup_call(match, index: int) -> dict[str, Any]:
    """Build one call from a markup match.

    Parameters
    ----------
    match : re.Match
        Match containing the tool name and argument block.
    index : int
        Zero-based call position.

    Returns
    -------
    dict[str, Any]
        OpenAI-compatible tool call.
    """
    name = match.group(1)
    arguments = _markup_arguments(match.group(2))
    return _call_document(name, arguments, index)


def _call_document(
    name: str, arguments: dict[str, Any], index: int
) -> dict[str, Any]:
    """Build the call envelope for one recovered tool call.

    Parameters
    ----------
    name : str
        Tool name.
    arguments : dict[str, Any]
        Parsed arguments.
    index : int
        Zero-based call position.

    Returns
    -------
    dict[str, Any]
        OpenAI-compatible tool call.
    """
    call = {"id": f"markup-{index}", "type": "function"}
    call["function"] = {
        "name": name,
        "arguments": json.dumps(arguments),
    }
    return call


def _markup_arguments(block: str) -> dict[str, Any]:
    """Parse argument key and value pairs from a markup block.

    Parameters
    ----------
    block : str
        Text between one opening and closing call tag.

    Returns
    -------
    dict[str, Any]
        Parsed arguments.
    """
    arguments: dict[str, Any] = {}
    for key, value in _MARKUP_ARG.findall(block):
        arguments[key.strip()] = _markup_value(value.strip())
    return arguments


def _markup_value(text: str) -> Any:
    """Decode one argument value as JSON when possible.

    Parameters
    ----------
    text : str
        Raw argument value.

    Returns
    -------
    Any
        Decoded value, or the original text when it is not JSON.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def _valid_calls(calls: list[dict[str, Any]], allowed: set) -> bool:
    """Return whether every parsed call names an executable tool.

    Parameters
    ----------
    calls : list of dict[str, Any]
        Parsed calls.
    allowed : set
        Tool names the registry can execute.

    Returns
    -------
    bool
        ``True`` when there is at least one call and every name is known.
    """
    if not calls:
        return False
    return all(call["function"]["name"] in allowed for call in calls)


def _strip_markup(content: str) -> str:
    """Remove tool-call markup from assistant text.

    Parameters
    ----------
    content : str
        Assistant text.

    Returns
    -------
    str
        Text without markup blocks.
    """
    cleaned = _MARKUP_GROUP.sub("", content)
    return _MARKUP_ONE.sub("", cleaned).strip()


def _final_text(message: dict[str, Any]) -> str:
    """Return the final answer text with any markup removed.

    Parameters
    ----------
    message : dict[str, Any]
        Assistant message.

    Returns
    -------
    str
        Clean answer text.
    """
    return _strip_markup(str(message.get("content") or ""))


def _system_prompt(lean: bool = False, repo: bool = False) -> str:
    """Build the combined interactive system prompt.

    Parameters
    ----------
    lean : bool
        Use the short repo-editing prompt.
    repo : bool
        Use the existing-repository prompt.

    Returns
    -------
    str
        Agent prompt, optionally followed by coding standards.
    """
    if repo:
        return _load_prompt("repo")
    if lean:
        return _load_prompt("lean")
    return _full_prompt()


def _full_prompt() -> str:
    """Build the default prompt with coding standards.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Agent prompt followed by coding standards.
    """
    return _load_prompt("agent") + "\n\n" + _load_prompt("coding_standards")


_SECRET_KEYS = (
    "secret",
    "token",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
)
_MAX_ARG_CHARS = 200
_MAX_RESULT_CHARS = 280


def _redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of tool arguments with secrets masked.

    Parameters
    ----------
    arguments : dict[str, Any]
        Parsed tool arguments.

    Returns
    -------
    dict[str, Any]
        Arguments safe to log and review.
    """
    if not isinstance(arguments, dict):
        return {"value": _short_value(arguments)}
    return {
        str(key): _redact_value(key, value) for key, value in arguments.items()
    }


def _redact_value(key: Any, value: Any) -> Any:
    """Redact or shorten one argument value.

    Parameters
    ----------
    key : Any
        Argument name.
    value : Any
        Argument value.

    Returns
    -------
    Any
        Redacted or truncated value.
    """
    if any(word in str(key).lower() for word in _SECRET_KEYS):
        return "[redacted]"
    return _short_value(value)


def _short_value(value: Any) -> Any:
    """Shorten a long string argument.

    Parameters
    ----------
    value : Any
        Argument value.

    Returns
    -------
    Any
        String capped at the maximum length, otherwise unchanged.
    """
    if isinstance(value, str):
        return value[:_MAX_ARG_CHARS]
    return value


def _result_head(content: str) -> str:
    """Return a short readable head of a tool result.

    Parameters
    ----------
    content : str
        Tool output string.

    Returns
    -------
    str
        Leading text capped at the maximum length.
    """
    return str(content)[:_MAX_RESULT_CHARS]


def _trace_core(
    task: str, name: str, arguments: dict, status: str
) -> dict[str, Any]:
    """Build the common fields of one execution record.

    Parameters
    ----------
    task : str
        Task identifier.
    name : str
        Tool name.
    arguments : dict
        Parsed tool arguments.
    status : str
        Status label.

    Returns
    -------
    dict[str, Any]
        Partial execution record.
    """
    entry = {"task": task, "tool": name, "status": status}
    entry["at"] = round(time.time(), 3)
    entry["arguments"] = _redact_arguments(arguments)
    entry["used_in_final"] = False
    return entry


def _retry_of(
    trace: list[dict[str, Any]], name: str, arguments: dict
) -> str | None:
    """Return the id of an earlier identical call.

    Parameters
    ----------
    trace : list of dict[str, Any]
        Earlier execution records.
    name : str
        Tool name.
    arguments : dict
        Redacted tool arguments.

    Returns
    -------
    str or None
        Earlier call id when the same call was already recorded.
    """
    signature = _signature(name, arguments)
    for entry in reversed(trace):
        if _signature(entry.get("tool"), entry.get("arguments")) == signature:
            return entry.get("id")
    return None


def _signature(name: Any, arguments: Any) -> str:
    """Return a stable signature for one tool call.

    Parameters
    ----------
    name : Any
        Tool name.
    arguments : Any
        Tool arguments.

    Returns
    -------
    str
        Signature string.
    """
    try:
        text = json.dumps(arguments, sort_keys=True)
    except (TypeError, ValueError):
        text = str(arguments)
    return f"{name}:{text}"


def _trace_used(entry: dict[str, Any], answer: str) -> bool:
    """Return whether a call's file or source appears in the answer.

    Parameters
    ----------
    entry : dict[str, Any]
        Execution record.
    answer : str
        Final answer text.

    Returns
    -------
    bool
        ``True`` when a path or result URL is cited.
    """
    arguments = entry.get("arguments") or {}
    path = str(arguments.get("path") or "")
    if path and path in answer:
        return True
    result = str(entry.get("result") or "")
    return any(url in answer for url in _urls(result))


def _urls(text: str) -> list[str]:
    """Return URLs found in a result excerpt.

    Parameters
    ----------
    text : str
        Result excerpt.

    Returns
    -------
    list of str
        Extracted URLs.
    """
    return re.findall(r"https?://[^\s)\]\"'<>]+", text)


def _append_trace_record(entry: dict[str, Any]) -> None:
    """Append one execution record when HARNESS_TRACE_LOG is set.

    Parameters
    ----------
    entry : dict[str, Any]
        Execution record.

    Returns
    -------
    None
        The record is appended to the log path when configured.
    """
    path = os.getenv("HARNESS_TRACE_LOG")
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, default=str) + "\n")


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


def _base_payload(
    prompt: str,
    answer: str,
    messages: list[dict[str, Any]],
    tool_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the reviewer payload without workspace artifacts.

    Parameters
    ----------
    prompt : str
        User question.
    answer : str
        Draft final answer.
    messages : list of dict[str, Any]
        Conversation messages.
    tool_trace : list of dict[str, Any] or None
        Auditable tool invocation records.

    Returns
    -------
    dict[str, Any]
        Question, answer, tool evidence, and tool trace.
    """
    recorded = "recorded" if tool_trace else "none"
    return {
        "question": prompt,
        "answer": answer,
        "tool_evidence": _tool_evidence(messages),
        "tool_trace": tool_trace or [],
        "tool_trace_origin": recorded,
    }


def _workspace_state(root: Path) -> dict[str, tuple[int, int]]:
    """Record size and modification time for workspace files.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    dict[str, tuple[int, int]]
        Relative path to modification time and size.
    """
    state: dict[str, tuple[int, int]] = {}
    for path in _scan_workspace_files(root):
        stamp = _file_stamp(path)
        if stamp is not None:
            state[str(path.relative_to(root))] = stamp
    return state


def _scan_workspace_files(root: Path) -> list[Path]:
    """List workspace files, skipping dependency and cache folders.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    list of pathlib.Path
        Regular files under the workspace.
    """
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in _SKIP_DIRS]
        for name in names:
            path = Path(current, name)
            if not path.is_symlink():
                files.append(path)
    return files


def _file_stamp(path: Path) -> tuple[int, int] | None:
    """Return a change stamp for one file.

    Parameters
    ----------
    path : pathlib.Path
        File to inspect.

    Returns
    -------
    tuple[int, int] or None
        Modification time and size, or ``None`` when missing.
    """
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _diff_paths(
    before: dict[str, tuple[int, int]],
    after: dict[str, tuple[int, int]],
) -> list[str]:
    """Return paths that are new or changed between two states.

    Parameters
    ----------
    before : dict[str, tuple[int, int]]
        Earlier workspace state.
    after : dict[str, tuple[int, int]]
        Later workspace state.

    Returns
    -------
    list of str
        New or modified relative paths.
    """
    paths: list[str] = []
    for path, stamp in after.items():
        if before.get(path) != stamp:
            paths.append(path)
    return paths


def _unique(paths: list[str]) -> list[str]:
    """Return paths in first-seen order without duplicates.

    Parameters
    ----------
    paths : list of str
        Candidate paths.

    Returns
    -------
    list of str
        Unique non-empty paths.
    """
    unique: list[str] = []
    for path in paths:
        if path and path not in unique:
            unique.append(path)
    return unique


def _with_artifacts(
    payload: dict[str, Any],
    messages: list[dict[str, Any]],
    root: Path,
    before: dict[str, tuple[int, int]] | None,
) -> dict[str, Any]:
    """Attach changed file contents to a reviewer payload.

    Parameters
    ----------
    payload : dict[str, Any]
        Base reviewer payload.
    messages : list of dict[str, Any]
        Conversation messages.
    root : pathlib.Path
        Workspace root.
    before : dict[str, tuple[int, int]] or None
        Pre-run workspace state.

    Returns
    -------
    dict[str, Any]
        Payload with an ``artifacts`` field when files changed.
    """
    artifacts = _artifact_evidence(messages, root, before)
    if artifacts:
        payload["artifacts"] = artifacts
    return payload


def _prior_requests(messages: list[dict[str, Any]], start: int) -> list[str]:
    """Return earlier user requests before the current task.

    Parameters
    ----------
    messages : list of dict[str, Any]
        Conversation messages.
    start : int
        Index of the current task's user message.

    Returns
    -------
    list of str
        Up to five earlier requests, each bounded.
    """
    requests = [
        str(message.get("content") or "")[:200]
        for message in messages[:start]
        if message.get("role") == "user"
    ]
    return requests[-5:]


def _task_changed(
    paths: list[str],
    root: Path,
    before: dict[str, tuple[int, int]] | None,
) -> list[str]:
    """Return current-run changed paths with workspace diffs.

    Parameters
    ----------
    paths : list of str
        Paths touched by current-run edit calls.
    root : pathlib.Path
        Workspace root.
    before : dict[str, tuple[int, int]] or None
        Pre-run workspace state.

    Returns
    -------
    list of str
        Unique current-run paths.
    """
    if before is None:
        return paths
    current = _diff_paths(before, _workspace_state(root))
    return _unique(current + paths)


def _artifact_evidence(
    messages: list[dict[str, Any]],
    root: Path,
    before: dict[str, tuple[int, int]] | None,
) -> list[dict[str, str]]:
    """Collect final contents of files changed by the agent.

    Parameters
    ----------
    messages : list of dict[str, Any]
        Conversation messages.
    root : pathlib.Path
        Workspace root.
    before : dict[str, tuple[int, int]] or None
        Pre-run workspace state.

    Returns
    -------
    list of dict[str, str]
        Bounded path and content pairs for recent mutations.
    """
    changed: list[str] = []
    if before is not None:
        changed = _diff_paths(before, _workspace_state(root))
    paths = _unique(changed + _changed_paths(messages))
    return _read_artifacts(paths, root)


def _changed_paths(messages: list[dict[str, Any]]) -> list[str]:
    """Return unique file paths touched by edit tools.

    Parameters
    ----------
    messages : list of dict[str, Any]
        Conversation messages.

    Returns
    -------
    list of str
        Paths in first-seen order.
    """
    paths: list[str] = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            path = _call_path(call)
            if path and path not in paths:
                paths.append(path)
    return paths


def _call_path(call: dict[str, Any]) -> str:
    """Return the path argument of one mutating tool call.

    Parameters
    ----------
    call : dict[str, Any]
        Tool call entry.

    Returns
    -------
    str
        Workspace path, or an empty string when absent.
    """
    function = call.get("function", {})
    if function.get("name") not in _EDIT_TOOLS:
        return ""
    try:
        arguments = json.loads(function.get("arguments", "{}"))
    except (json.JSONDecodeError, TypeError):
        return ""
    return str(arguments.get("path", ""))


def _read_artifacts(paths: list[str], root: Path) -> list[dict[str, str]]:
    """Read the newest changed files for reviewer context.

    Parameters
    ----------
    paths : list of str
        Changed workspace paths.
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    list of dict[str, str]
        Readable path and content pairs.
    """
    artifacts: list[dict[str, str]] = []
    for raw in paths[-_ARTIFACT_FILES:]:
        artifact = _read_artifact(raw, root)
        if artifact is not None:
            artifacts.append(artifact)
    return artifacts


def _read_artifact(raw: str, root: Path) -> dict[str, str] | None:
    """Read one changed file if it is safe and text.

    Parameters
    ----------
    raw : str
        Workspace path.
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    dict[str, str] or None
        Path and bounded content, or ``None`` when unreadable.
    """
    try:
        target = _confined_path(raw, root)
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return {"path": raw, "content": _bounded_artifact(content)}


def _bounded_artifact(content: str) -> str:
    """Bound one artifact so the review context stays small.

    Parameters
    ----------
    content : str
        Full file contents.

    Returns
    -------
    str
        Contents truncated at the artifact limit.
    """
    if len(content) <= _ARTIFACT_CHARS:
        return content
    return content[:_ARTIFACT_CHARS] + "\n...[truncated]"


def _confined_path(raw: str, root: Path) -> Path:
    """Resolve a path and reject escapes from the workspace.

    Parameters
    ----------
    raw : str
        Workspace path.
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    pathlib.Path
        Confined absolute path.
    """
    target = (root / raw).resolve()
    if target != root and root not in target.parents:
        raise ValueError("artifact escapes workspace")
    return target


def _append_review_log(record: dict[str, Any]) -> None:
    """Append one review event when HARNESS_REVIEW_LOG is set.

    Parameters
    ----------
    record : dict[str, Any]
        Review event fields.

    Returns
    -------
    None
        The event is appended to the log path when configured.
    """
    path = os.getenv("HARNESS_REVIEW_LOG")
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, default=str) + "\n")


def _review_call(
    client: Any, system: str, user: str, saved: list[Any]
) -> None:
    """Run one review call, recording its response or error.

    Parameters
    ----------
    client : Any
        Client exposing ``complete``.
    system : str
        Review instruction.
    user : str
        Review payload.
    saved : list of Any
        Collector for the response or exception.

    Returns
    -------
    None
        The collector receives exactly one value.
    """
    try:
        saved.append(client.complete(system, user))
    except Exception as exc:
        saved.append(exc)


def _ledger_mode() -> str:
    """Return the configured ledger mode.

    Parameters
    ----------
    None

    Returns
    -------
    str
        ``off``, ``auto``, or ``on``.
    """
    value = os.getenv("HARNESS_ANSWER_LEDGER", "auto").strip().lower()
    if value in ("0", "false", "no", "off"):
        return "off"
    if value in ("", "auto"):
        return "auto"
    return "on"


def _requirement_context(history: list[str], prompt: str, answer: str) -> str:
    """Build the requirement extraction payload.

    Parameters
    ----------
    history : list of str
        Earlier user requests.
    prompt : str
        Current user question.
    answer : str
        Draft answer.

    Returns
    -------
    str
        JSON payload for the extractor.
    """
    return json.dumps(
        {
            "prior_requests": history,
            "question": prompt,
            "answer": answer,
        }
    )


def _ledger_value(raw: str) -> dict | None:
    """Decode a ledger response into a mapping.

    Parameters
    ----------
    raw : str
        Raw model response.

    Returns
    -------
    dict or None
        Decoded ledger, or ``None`` when invalid.
    """
    try:
        value = json_value(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _verification_issues(
    prompt: str, answer: str, ledger: dict | None
) -> list[str]:
    """Combine limit checks with ledger arithmetic issues.

    Parameters
    ----------
    prompt : str
        User question.
    answer : str
        Draft answer.
    ledger : dict or None
        Extracted numeric ledger.

    Returns
    -------
    list of str
        Limit violations and ledger issues.
    """
    issues = limit_issues(prompt, answer)
    if ledger is None:
        return issues
    issues.extend(ledger_issues(ledger))
    return issues


def _applicable_ledger(value: dict, record) -> dict | None:
    """Return the ledger only when the extractor marked it applicable.

    Parameters
    ----------
    value : dict
        Decoded ledger.
    record : collections.abc.Callable
        Event recorder.

    Returns
    -------
    dict or None
        Ledger, or ``None`` when it does not apply.
    """
    if value.get("applies") is False:
        record("ledger", "not_applicable")
        return None
    return value


def _invariant_mode() -> str:
    """Return the configured invariant mode.

    Parameters
    ----------
    None

    Returns
    -------
    str
        ``off``, ``auto``, or ``on``.
    """
    value = os.getenv("HARNESS_ANSWER_INVARIANTS", "auto").strip().lower()
    if value in ("0", "false", "no", "off"):
        return "off"
    if value in ("", "auto"):
        return "auto"
    return "on"


def _requirement_mode() -> str:
    """Return the configured requirement-check mode.

    Parameters
    ----------
    None

    Returns
    -------
    str
        ``off``, ``auto``, or ``on``.
    """
    value = os.getenv("HARNESS_REQUIREMENT_CHECK", "auto").strip().lower()
    if value in ("0", "false", "no", "off"):
        return "off"
    if value in ("", "auto"):
        return "auto"
    return "on"


def _invariant_value(raw: str) -> dict | None:
    """Decode an invariant response into a mapping.

    Parameters
    ----------
    raw : str
        Raw model response.

    Returns
    -------
    dict or None
        Decoded verdict, or ``None`` when invalid.
    """
    try:
        value = json_value(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _invariant_context(prompt: str, answer: str, rules: list[str]) -> str:
    """Build the invariant checker payload.

    Parameters
    ----------
    prompt : str
        User question.
    answer : str
        Draft answer.
    rules : list of str
        Selected invariants.

    Returns
    -------
    str
        JSON payload.
    """
    return json.dumps(
        {"question": prompt, "answer": answer, "invariants": rules}
    )


def _violations(data: dict) -> list[str]:
    """Return formatted violated-invariant findings.

    Parameters
    ----------
    data : dict
        Decoded invariant verdict.

    Returns
    -------
    list of str
        Violation messages.
    """
    issues = []
    for item in data.get("violations") or []:
        if isinstance(item, dict) and item.get("verdict") == "violated":
            issues.append(_violation_text(item))
    return issues


def _violation_text(item: dict) -> str:
    """Format one violated invariant.

    Parameters
    ----------
    item : dict
        Violation entry.

    Returns
    -------
    str
        Human-readable violation.
    """
    rule = str(item.get("invariant") or "invariant")
    detail = str(item.get("detail") or item.get("claim") or "")
    return f"{rule}: {detail}".strip(": ")


def _review_mode(review: dict) -> str:
    """Return the reviewer mode or ``legacy``.

    Parameters
    ----------
    review : dict
        Decoded reviewer verdict.

    Returns
    -------
    str
        One of the review modes, or ``legacy`` when absent.
    """
    mode = str(review.get("mode", "")).strip().lower()
    if mode in _REVIEW_MODES:
        return mode
    return "legacy"


def _blocking_review(review: dict, mode: str) -> bool:
    """Return whether a review found a concrete blocking defect.

    Parameters
    ----------
    review : dict
        Decoded reviewer verdict.
    mode : str
        Review mode.

    Returns
    -------
    bool
        ``True`` when a blocking issue is present.
    """
    if mode == "legacy":
        return review.get("approved") is False
    issues = review.get("issues") or []
    return any(_blocking_issue(issue, mode) for issue in issues)


def _blocking_issue(issue: Any, mode: str) -> bool:
    """Return whether one issue blocks delivery.

    Parameters
    ----------
    issue : Any
        Decoded issue entry.
    mode : str
        Review mode.

    Returns
    -------
    bool
        ``True`` for a high or medium defect that the mode blocks on.
    """
    if not isinstance(issue, dict):
        return False
    if issue.get("severity") not in ("high", "medium"):
        return False
    kind = issue.get("kind")
    if mode == "advisory":
        return kind == "incorrect"
    return kind in ("incorrect", "unsupported")


def _allow_revision(
    mode: str, answer: str, revised: Any, blocking: bool
) -> bool:
    """Return whether a reviewer replacement should be applied.

    Parameters
    ----------
    mode : str
        Review mode.
    answer : str
        Original draft answer.
    revised : Any
        Reviewer replacement, if any.
    blocking : bool
        Whether a concrete defect was found.

    Returns
    -------
    bool
        ``True`` when the replacement should replace the answer.
    """
    if not isinstance(revised, str) or not revised.strip():
        return False
    if _has_code_block(answer):
        return False
    if mode == "legacy" or blocking:
        return True
    return len(revised.strip()) >= _revision_floor(answer)


def _has_code_block(text: str) -> bool:
    """Return whether a text contains a fenced code block.

    Parameters
    ----------
    text : str
        Text to scan.

    Returns
    -------
    bool
        Whether a triple-backtick fence appears.
    """
    return "```" in text


def _revision_floor(answer: str) -> float:
    """Return the smallest caveat-only replacement length.

    Parameters
    ----------
    answer : str
        Original draft answer.

    Returns
    -------
    float
        Ninety percent of the stripped original length.
    """
    return 0.9 * len(answer.strip())


def _review_response(value: Any) -> str:
    """Return a review response or re-raise a worker error.

    Parameters
    ----------
    value : Any
        Collected response or exception.

    Returns
    -------
    str
        Reviewer response text.
    """
    if isinstance(value, Exception):
        raise value
    return str(value)


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


def _head_messages(
    messages: list[dict[str, Any]], keep: int
) -> list[dict[str, Any]]:
    """Return pinned messages for context compaction.

    Parameters
    ----------
    messages : list of dict[str, Any]
        Conversation messages.
    keep : int
        Number of newest messages to retain.

    Returns
    -------
    list of dict[str, Any]
        Pinned system, initial user, and latest dropped user message.
    """
    head = _initial_head(messages)
    latest = _latest_user_index(messages)
    if latest is not None and latest < len(messages) - keep:
        if latest >= len(head):
            head.append(messages[latest])
    return head


def _initial_head(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the system message and initial user task.

    Parameters
    ----------
    messages : list of dict[str, Any]
        Conversation messages.

    Returns
    -------
    list of dict[str, Any]
        Pinned initial messages.
    """
    if len(messages) >= 2 and messages[1].get("role") == "user":
        return messages[:2]
    return messages[:1]


def _latest_user_index(messages: list[dict[str, Any]]) -> int | None:
    """Return the newest user message index.

    Parameters
    ----------
    messages : list of dict[str, Any]
        Conversation messages.

    Returns
    -------
    int or None
        Index of the newest user message.
    """
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            return index
    return None


def _is_test_command(arguments: str) -> bool:
    """Return whether tool arguments request a test command.

    Parameters
    ----------
    arguments : str
        JSON tool arguments.

    Returns
    -------
    bool
        ``True`` for pytest, unittest, or compile commands.
    """
    try:
        command = json.loads(arguments).get("command", "")
    except (json.JSONDecodeError, TypeError):
        return False
    markers = ("pytest", "unittest", "test_", "compileall")
    return any(marker in command for marker in markers)


def _profile_context_chars(client: Any) -> int:
    """Return the profile context character limit for a client.

    Parameters
    ----------
    client : Any
        Chat model client.

    Returns
    -------
    int
        Character limit from matching profile, or default.
    """
    model = getattr(client, "model", "")
    if isinstance(model, str) and model:
        return profile_for(model).context_chars
    return _CONTEXT_CHARS


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


def _repair_attempts() -> int:
    """Return the bounded number of reviewer-test repair turns.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Repair attempts, at least one.
    """
    raw = os.getenv("HARNESS_REPAIR_ATTEMPTS", "2").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


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


def _auto_verify_enabled() -> bool:
    """Return whether project-test verification is enabled.

    Parameters
    ----------
    None

    Returns
    -------
    bool
        Whether ``HARNESS_AUTO_VERIFY`` enables verification.
    """
    value = os.getenv("HARNESS_AUTO_VERIFY", "0").strip().lower()
    return value in ("1", "true", "yes", "on")


def _verify_attempts() -> int:
    """Return the bounded number of project-test repair turns.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Repair attempts, at least one.
    """
    raw = os.getenv("HARNESS_VERIFY_ATTEMPTS", "2").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


def _has_pytest(root: Path) -> bool:
    """Return whether a workspace looks like a pytest project.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    bool
        ``True`` when pytest-style tests are present.
    """
    if (root / "conftest.py").exists() or (root / "tests").is_dir():
        return True
    return any(root.glob("test_*.py"))


def _test_command(root: Path) -> list[str]:
    """Return the project's test command.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    list[str]
        Container-neutral test command.
    """
    if _has_pytest(root):
        return ["python", "-m", "pytest", "-q"]
    return ["python", "-m", "unittest", "discover", "-q"]


def _run_local_tests(root: Path, command: list[str]) -> tuple[bool, str]:
    """Run project tests on the host.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    command : list[str]
        Container-neutral test command.

    Returns
    -------
    tuple[bool, str]
        Whether tests passed, and combined output.
    """
    result = _local_process(root, command)
    output = f"{result.stdout}\n{result.stderr}".strip()
    return result.returncode == 0, output


def _local_process(root: Path, command: list[str]):
    """Run a host test command.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    command : list[str]
        Container-neutral test command.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Completed process.
    """
    return subprocess.run(
        [sys.executable, *command[1:]],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _verify_message(output: str) -> dict[str, str]:
    """Build the message that requests a project-test repair.

    Parameters
    ----------
    output : str
        Failing test output.

    Returns
    -------
    dict[str, str]
        Repair message.
    """
    detail = _compact_test_output(output)
    content = (
        "The project tests fail. Fix only the failing tests, then finish.\n"
    )
    return {"role": "user", "content": content + detail}


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
