"""Pi-like stateful tool-calling agent runtime."""

import json
from pathlib import Path
from typing import Any

from .openrouter import OpenRouterClient
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

        Returns
        -------
        None
            This initializer configures the agent.
        """
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
        return session.messages[:] if session else []

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
        return self._loop()

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
        return "Agent stopped after reaching the turn limit."

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
        try:
            arguments = json.loads(function.get("arguments", "{}"))
            content = self.tools.execute(function["name"], arguments)
        except (ToolError, json.JSONDecodeError, KeyError) as exc:
            content = json.dumps({"error": str(exc)})
        return {"role": "tool", "tool_call_id": call["id"], "content": content}
