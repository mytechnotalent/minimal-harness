"""Tests for custom agent system prompts used by research mode."""

import tempfile
import unittest
from pathlib import Path

from meta_harness.agent import Agent
from meta_harness.session import Session


def _agent(folder, session, prompt):
    """Build an agent with a stub client.

    Parameters
    ----------
    folder : str
        Workspace root.
    session : Session
        Persisted session.
    prompt : str or None
        System prompt override.

    Returns
    -------
    Agent
        Configured agent.
    """
    return Agent(
        root=folder,
        client=object(),
        session=session,
        system_prompt=prompt,
    )


class ResearchPromptTests(unittest.TestCase):
    """Verify research prompts replace coding prompts in the transcript."""

    def test_custom_prompt_is_used_for_new_session(self) -> None:
        """Start an empty session with the custom prompt.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The first message is the custom prompt.
        """
        with tempfile.TemporaryDirectory() as folder:
            session = Session(Path(folder) / "transcript.jsonl")
            agent = _agent(folder, session, "RESEARCH PROMPT")
            messages = agent._initial_messages(session)
        self.assertEqual(messages[0]["content"], "RESEARCH PROMPT")

    def test_custom_prompt_replaces_existing_system_message(self) -> None:
        """Replace a prior system message with the custom prompt.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The old prompt is gone and history remains.
        """
        with tempfile.TemporaryDirectory() as folder:
            session = Session(Path(folder) / "transcript.jsonl")
            session.append({"role": "system", "content": "OLD"})
            session.append({"role": "user", "content": "hello"})
            agent = _agent(folder, session, "RESEARCH PROMPT")
            messages = agent._initial_messages(session)
        self.assertEqual(messages[0]["content"], "RESEARCH PROMPT")
        self.assertEqual(len(messages), 2)


if __name__ == "__main__":
    unittest.main()
