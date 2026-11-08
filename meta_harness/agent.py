"""Pi-like stateful tool-calling agent runtime."""

import json
import os
from pathlib import Path
from typing import Any

from ._json_util import json_value
from .openrouter import OpenRouterClient
from .prompts import load as _load_prompt
from .session import Session
from .tools import ToolError, ToolRegistry


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
        system = (
            _load_prompt("agent") + "\n\n" + _load_prompt("coding_standards")
        )
        return [{"role": "system", "content": system}] + messages

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
        self._append({"role": "user", "content": prompt})
        return self._review_answer(prompt, self._loop())

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
        if not self._review_enabled():
            return answer
        review = self._answer_review(prompt, answer)
        revised = review.get("revised_answer")
        if self._rejected(review) and isinstance(revised, str):
            return revised.strip() or answer
        return answer

    def _review_enabled(self) -> bool:
        """Return whether answer review is enabled.

        Returns
        -------
        bool
            ``True`` when configured and the client supports completion.
        """
        value = os.getenv("HARNESS_ANSWER_REVIEW", "1").strip().lower()
        enabled = value not in ("0", "false", "no")
        return enabled and hasattr(self.client, "complete")

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
            raw = self.client.complete(
                _load_prompt("answer_reviewer"),
                self._review_context(prompt, answer),
            )
            value = json_value(raw)
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

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
        evidence = [
            str(message.get("content", ""))[-500:]
            for message in self.messages
            if message.get("role") == "tool"
        ][-8:]
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
        if not self.session:
            discarded = self.messages[:-keep]
            self.messages = self.messages[-keep:]
            return discarded
        discarded = self.session.compact(keep)
        self.messages = self.session.messages[:]
        return discarded

    def _loop(self) -> str:
        """Process model turns until completion.

        Returns
        -------
        str
            Final response or turn-limit message.
        """
        for _ in range(self.max_turns):
            message = self._message()
            if not message.get("tool_calls"):
                return str(message.get("content", ""))
            self._execute_calls(message["tool_calls"])
        return self._finalize()

    def _finalize(self) -> str:
        """Request a final answer without tools after the turn limit.

        Returns
        -------
        str
            Final assistant text, or a fallback message.
        """
        self._append(
            {
                "role": "system",
                "content": (
                    "Turn limit reached. Answer now using the information "
                    "already gathered. Do not call tools."
                ),
            }
        )
        response = self.client.chat(self.messages, [])
        message = response["choices"][0]["message"]
        self._append(message)
        return str(
            message.get("content")
            or "Agent stopped after reaching the turn limit."
        )

    def _message(self) -> dict[str, Any]:
        """Request and append one assistant message.

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
        arguments: dict[str, Any] = {}
        try:
            arguments = json.loads(function.get("arguments", "{}"))
            content = self.tools.execute(function["name"], arguments)
        except (ToolError, json.JSONDecodeError, KeyError) as exc:
            content = json.dumps({"error": str(exc)})
        if self.observer is not None:
            self.observer(function["name"], arguments, content)
        return {"role": "tool", "tool_call_id": call["id"], "content": content}


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
