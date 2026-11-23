"""Raw-model baseline runner with no harness validation layers."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from meta_harness.evalbench.cases import Case
from meta_harness.evalbench.cases import parse_arguments
from meta_harness.evalbench.common import core_record
from meta_harness.evalbench.common import delta
from meta_harness.evalbench.common import error_text
from meta_harness.evalbench.common import snapshot
from meta_harness.tools import ToolRegistry

DEFAULT_TURNS = 8


class BaselineRunner:
    """Run cases against the raw model with a minimal tool loop.

    The baseline uses the same model and the same tools as the harness
    configuration. It deliberately omits every harness layer: no answer
    review, no ledger, no invariants, no requirements, no adversarial
    drafts, no answer-time tests, and no repair turns.
    """

    def __init__(
        self,
        client: Any,
        root: Path | str | None = None,
        max_turns: int = DEFAULT_TURNS,
        web_enabled: bool = False,
    ) -> None:
        """Store the client, workspace, turn limit, and web policy.

        Parameters
        ----------
        client : Any
            Model client exposing ``chat`` or ``complete``.
        root : pathlib.Path or str or None
            Workspace root for the tool registry.
        max_turns : int
            Maximum tool-loop turns.
        web_enabled : bool
            Advertise web and browser tools.

        Returns
        -------
        None
            This initializer configures the runner.
        """
        self.client = client
        self.root = Path(root) if root else Path(".")
        self.max_turns = max_turns
        self.web_enabled = web_enabled

    def run_case(self, case: Case) -> dict[str, Any]:
        """Run one case and return its scored record.

        Parameters
        ----------
        case : Case
            The benchmark case.

        Returns
        -------
        dict[str, Any]
            Scored run record.
        """
        before = snapshot(self.client)
        started = time.monotonic()
        answer, calls, error = self._execute(case)
        usage = delta(before, snapshot(self.client))
        return self._record(case, answer, calls, error, usage, started)

    def _execute(self, case: Case) -> tuple[str, list[dict[str, Any]], str]:
        """Produce an answer, executed calls, and an error string.

        Parameters
        ----------
        case : Case
            The benchmark case.

        Returns
        -------
        tuple[str, list[dict[str, Any]], str]
            Answer text, tool calls, and error text (empty on success).
        """
        registry = self._registry(case)
        try:
            answer, calls = self._answer(case, registry)
            return answer, calls, ""
        except Exception as exc:
            return "", [], error_text(exc)

    def _registry(self, case: Case) -> ToolRegistry:
        """Build the tool registry for one case.

        Parameters
        ----------
        case : Case
            The benchmark case.

        Returns
        -------
        ToolRegistry
            Registry restricted to the case tools.
        """
        return ToolRegistry(
            self.root,
            web_enabled=self.web_enabled,
            allowed_tools=case.tools,
        )

    def _answer(
        self, case: Case, registry: ToolRegistry
    ) -> tuple[str, list[dict[str, Any]]]:
        """Choose the raw completion path for one case.

        Parameters
        ----------
        case : Case
            The benchmark case.
        registry : ToolRegistry
            Tool registry for this case.

        Returns
        -------
        tuple[str, list[dict[str, Any]]]
            Answer text and executed tool calls.
        """
        if hasattr(self.client, "chat"):
            return self._tool_loop(case, registry)
        return self.client.complete(case.system, case.prompt, 0.0), []

    def _tool_loop(
        self, case: Case, registry: ToolRegistry
    ) -> tuple[str, list[dict[str, Any]]]:
        """Run the minimal model-tool loop without harness layers.

        Parameters
        ----------
        case : Case
            The benchmark case.
        registry : ToolRegistry
            Tool registry for this case.

        Returns
        -------
        tuple[str, list[dict[str, Any]]]
            Final text and executed tool calls.
        """
        messages = self._initial_messages(case)
        schemas = case.schemas or registry.schema(names=case.tools)
        return self._loop_turns(messages, schemas, registry)

    def _loop_turns(
        self,
        messages: list[dict[str, Any]],
        schemas: list[dict[str, Any]],
        registry: ToolRegistry,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Run tool-loop turns until final text or the turn limit.

        Parameters
        ----------
        messages : list[dict[str, Any]]
            Conversation so far.
        schemas : list[dict[str, Any]]
            Tool schemas.
        registry : ToolRegistry
            Tool registry for this case.

        Returns
        -------
        tuple[str, list[dict[str, Any]]]
            Final text and executed tool calls.
        """
        calls: list[dict[str, Any]] = []
        for _ in range(self.max_turns):
            result = self._run_turn(messages, schemas, registry)
            calls.extend(result["calls"])
            if result["done"]:
                return str(result["text"]), calls
            messages = result["messages"]
        return str(_final_text(messages)), calls

    def _run_turn(
        self,
        messages: list[dict[str, Any]],
        schemas: list[dict[str, Any]],
        registry: ToolRegistry,
    ) -> dict[str, Any]:
        """Execute one model turn and, when tools fire, their results.

        Parameters
        ----------
        messages : list[dict[str, Any]]
            Conversation so far.
        schemas : list[dict[str, Any]]
            Tool schemas.
        registry : ToolRegistry
            Tool registry for this case.

        Returns
        -------
        dict[str, Any]
            Done flag, final text, new messages, and new tool calls.
        """
        message = _assistant_message(self.client.chat(messages, schemas))
        calls = _message_calls(message)
        if message.get("tool_calls"):
            return _tool_result(messages, message, calls, registry)
        return _text_result(message, calls, messages)

    def _initial_messages(self, case: Case) -> list[dict[str, Any]]:
        """Build the first message list for a case.

        Parameters
        ----------
        case : Case
            The benchmark case.

        Returns
        -------
        list[dict[str, Any]]
            System and user messages.
        """
        messages: list[dict[str, Any]] = []
        if case.system:
            messages.append({"role": "system", "content": case.system})
        messages.append({"role": "user", "content": case.prompt})
        return messages

    def _record(
        self,
        case: Case,
        answer: str,
        calls: list[dict[str, Any]],
        error: str,
        usage: dict[str, float],
        started: float,
    ) -> dict[str, Any]:
        """Build the scored run record with usage fields.

        Parameters
        ----------
        case : Case
            The benchmark case.
        answer : str
            Final answer text.
        calls : list[dict[str, Any]]
            Executed tool calls.
        error : str
            Error text, empty on success.
        usage : dict[str, float]
            Usage deltas for the case.
        started : float
            Monotonic start time.

        Returns
        -------
        dict[str, Any]
            Complete scored run record.
        """
        record = core_record(case, answer, calls, error, started)
        record.update(usage)
        return record


def _assistant_message(body: dict[str, Any]) -> dict[str, Any]:
    """Extract the assistant message from a chat response.

    Parameters
    ----------
    body : dict[str, Any]
        Provider response body.

    Returns
    -------
    dict[str, Any]
        Assistant message, or an empty fallback.
    """
    choices = body.get("choices") or []
    if not choices:
        return {"role": "assistant", "content": ""}
    return choices[0].get("message") or {"role": "assistant", "content": ""}


def _message_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Return executed tool calls from one assistant message.

    Parameters
    ----------
    message : dict[str, Any]
        Assistant message.

    Returns
    -------
    list[dict[str, Any]]
        Raw tool calls.
    """
    return list(message.get("tool_calls") or [])


def _tool_result(
    messages: list[dict[str, Any]],
    message: dict[str, Any],
    calls: list[dict[str, Any]],
    registry: ToolRegistry,
) -> dict[str, Any]:
    """Build a turn result that executes tool calls.

    Parameters
    ----------
    messages : list[dict[str, Any]]
        Conversation so far.
    message : dict[str, Any]
        Assistant message with tool calls.
    calls : list[dict[str, Any]]
        Raw tool calls.
    registry : ToolRegistry
        Tool registry for this case.

    Returns
    -------
    dict[str, Any]
        Incomplete turn result with updated messages.
    """
    updated = _append_results(messages, message, registry)
    return {"done": False, "text": "", "calls": calls, "messages": updated}


def _text_result(
    message: dict[str, Any],
    calls: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a final-text turn result.

    Parameters
    ----------
    message : dict[str, Any]
        Assistant message without tool calls.
    calls : list[dict[str, Any]]
        Tool calls collected so far.
    messages : list[dict[str, Any]]
        Conversation so far.

    Returns
    -------
    dict[str, Any]
        Complete turn result with final text.
    """
    text = str(message.get("content", ""))
    return {"done": True, "text": text, "calls": calls, "messages": messages}


def _append_results(
    messages: list[dict[str, Any]],
    message: dict[str, Any],
    registry: ToolRegistry,
) -> list[dict[str, Any]]:
    """Append an assistant message and its tool results.

    Parameters
    ----------
    messages : list[dict[str, Any]]
        Conversation so far.
    message : dict[str, Any]
        Assistant message with tool calls.
    registry : ToolRegistry
        Tool registry for this case.

    Returns
    -------
    list[dict[str, Any]]
        Extended conversation.
    """
    updated = list(messages)
    updated.append(message)
    for call in message.get("tool_calls") or []:
        updated.append(_result_message(call, registry))
    return updated


def _result_message(
    call: dict[str, Any], registry: ToolRegistry
) -> dict[str, Any]:
    """Execute one tool call and format its result message.

    Parameters
    ----------
    call : dict[str, Any]
        Raw tool call.
    registry : ToolRegistry
        Tool registry for this case.

    Returns
    -------
    dict[str, Any]
        Tool result message.
    """
    name = str(call.get("function", {}).get("name", ""))
    arguments = parse_arguments(call.get("function", {}).get("arguments"))
    content = _execute_tool(registry, name, arguments)
    identifier = call.get("id", "")
    payload = {"role": "tool", "tool_call_id": identifier}
    payload["content"] = str(content)
    return payload


def _execute_tool(
    registry: ToolRegistry, name: str, arguments: dict[str, Any]
) -> str:
    """Execute one tool call and bound failures.

    Parameters
    ----------
    registry : ToolRegistry
        Tool registry for the case.
    name : str
        Tool name.
    arguments : dict[str, Any]
        Tool arguments.

    Returns
    -------
    str
        Tool result or a bounded error string.
    """
    try:
        return str(registry.execute(name, arguments))
    except Exception as exc:
        return f"tool error: {error_text(exc)}"


def _final_text(messages: list[dict[str, Any]]) -> str:
    """Return the last assistant content in a message list.

    Parameters
    ----------
    messages : list[dict[str, Any]]
        Conversation messages.

    Returns
    -------
    str
        Last assistant text, or empty.
    """
    for message in reversed(messages):
        if message.get("role") == "assistant":
            return str(message.get("content", ""))
    return ""
