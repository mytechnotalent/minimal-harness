"""Verify ChatModel structural typing against real and test clients."""

import unittest

from meta_harness.chat_model import ChatModel
from meta_harness.openrouter import OpenRouterClient


class NotAModel:
    """Class that does not implement the ChatModel protocol."""


class MinimalModel:
    """Minimal object shaped like a ChatModel."""

    call_count = 0
    prompt_tokens = 0
    completion_tokens = 0

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return an empty completion."""
        return ""

    def usage_summary(self) -> str:
        """Return an empty usage summary."""
        return "calls=0 prompt_tokens=0 completion_tokens=0"


class ChatModelProtocolTests(unittest.TestCase):
    """Verify ChatModel structural typing."""

    def test_openrouter_client_satisfies_protocol(self) -> None:
        """OpenRouterClient is structurally a ChatModel."""
        self.assertIsInstance(OpenRouterClient(), ChatModel)

    def test_minimal_model_satisfies_protocol(self) -> None:
        """A minimal shape-compatible object is a ChatModel."""
        self.assertIsInstance(MinimalModel(), ChatModel)

    def test_bare_object_does_not_satisfy_protocol(self) -> None:
        """An unrelated object is not a ChatModel."""
        self.assertNotIsInstance(NotAModel(), ChatModel)


if __name__ == "__main__":
    unittest.main()
