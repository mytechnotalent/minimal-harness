"""Structural typing protocol for chat-completion clients."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ChatModel(Protocol):
    """Minimal chat-completion interface used by ``SearchPipeline``.

    Any object exposing this shape can drive proposer, reviewer, and
    adjudicator stages. ``OpenRouterClient`` satisfies it. A test double,
    a local model wrapper, or a future backend for a different provider
    can be substituted without touching pipeline code.

    Attributes
    ----------
    call_count : int
        Number of successful completions so far.
    prompt_tokens : int
        Cumulative prompt tokens reported by the provider.
    completion_tokens : int
        Cumulative completion tokens reported by the provider.
    """

    call_count: int
    prompt_tokens: int
    completion_tokens: int

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return one completion for a system + user prompt pair.

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
            Completion content.
        """
        ...

    def usage_summary(self) -> str:
        """Return a one-line summary of accumulated usage.

        Returns
        -------
        str
            Human-readable summary line.
        """
        ...
