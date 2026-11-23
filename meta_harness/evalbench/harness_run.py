"""Harness-enabled runner using the complete agent validation stack."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from meta_harness.agent import Agent
from meta_harness.evalbench.cases import Case
from meta_harness.evalbench.common import core_record
from meta_harness.evalbench.common import delta
from meta_harness.evalbench.common import error_text
from meta_harness.evalbench.common import snapshot
from meta_harness.tools import ToolRegistry

DEFAULT_TURNS = 12


class HarnessRunner:
    """Run cases through the complete agent stack.

    The harness configuration keeps every validation layer the product
    enables by default: answer review, ledger, invariants, requirements,
    adversarial drafts, answer-time tests, and repair turns. The model and
    tools are identical to the baseline configuration.
    """

    def __init__(
        self,
        client: Any,
        root: Path | str | None = None,
        max_turns: int = DEFAULT_TURNS,
        web_enabled: bool = False,
    ) -> None:
        """Store the client, workspace, and agent settings.

        Parameters
        ----------
        client : Any
            Model client.
        root : pathlib.Path or str or None
            Workspace root.
        max_turns : int
            Agent turn limit.
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
        """Run one case through the agent and return its record.

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
        """Run the agent and collect answer, calls, and error.

        Parameters
        ----------
        case : Case
            The benchmark case.

        Returns
        -------
        tuple[str, list[dict[str, Any]], str]
            Answer text, tool calls, and error text (empty on success).
        """
        agent = self._agent(case)
        try:
            answer = agent.run(case.prompt)
            return answer, _agent_calls(agent), ""
        except Exception as exc:
            return "", [], error_text(exc)

    def _agent(self, case: Case) -> Agent:
        """Build one agent for a case.

        Parameters
        ----------
        case : Case
            The benchmark case.

        Returns
        -------
        Agent
            Agent with a registry restricted to the case tools.
        """
        registry = ToolRegistry(
            self.root,
            web_enabled=self.web_enabled,
            allowed_tools=case.tools,
            extra_schemas=case.schemas,
        )
        return self._agent_with(registry)

    def _agent_with(self, registry: ToolRegistry) -> Agent:
        """Build an agent around one registry.

        Parameters
        ----------
        registry : ToolRegistry
            Tool registry for the case.

        Returns
        -------
        Agent
            Agent using the registry.
        """
        return Agent(
            root=self.root,
            client=self.client,
            max_turns=self.max_turns,
            web_enabled=self.web_enabled,
            tools=registry,
        )

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


def _agent_calls(agent: Agent) -> list[dict[str, Any]]:
    """Collect executed tool calls from agent messages.

    Parameters
    ----------
    agent : Agent
        The finished agent run.

    Returns
    -------
    list[dict[str, Any]]
        Raw tool calls in message order.
    """
    calls: list[dict[str, Any]] = []
    for message in agent.messages:
        if message.get("role") == "assistant":
            calls.extend(message.get("tool_calls") or [])
    return calls
