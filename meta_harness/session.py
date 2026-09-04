"""Persistent JSONL sessions for the interactive agent."""

import json
from pathlib import Path
from typing import Any


class Session:
    """Persist agent messages in a JSONL transcript."""

    def __init__(self, path: Path | str) -> None:
        """Initialize a session at a transcript path.

        Parameters
        ----------
        path : pathlib.Path or str
            JSONL transcript path.

        Returns
        -------
        None
            This initializer configures the session.
        """
        self.path = Path(path)
        self.messages: list[dict[str, Any]] = self._load()

    def append(self, message: dict[str, Any]) -> None:
        """Append one message to memory and disk.

        Parameters
        ----------
        message : dict[str, Any]
            Message to persist.

        Returns
        -------
        None
            The message is appended to the transcript.
        """
        self.messages.append(message)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(message, default=str) + "\n")

    def branch(self, path: Path | str) -> "Session":
        """Create a branched transcript containing current messages.

        Parameters
        ----------
        path : pathlib.Path or str
            Destination transcript path.

        Returns
        -------
        Session
            New session with copied messages.
        """
        child = Session(path)
        for message in self.messages:
            child.append(message)
        return child

    def compact(self, keep: int = 20) -> list[dict[str, Any]]:
        """Keep the newest messages and return discarded messages.

        Parameters
        ----------
        keep : int
            Number of newest messages to retain.

        Returns
        -------
        list[dict[str, Any]]
            Messages removed from the in-memory context.
        """
        discarded = self.messages[:-keep] if keep else self.messages[:]
        self.messages = self.messages[-keep:] if keep else []
        return discarded

    def _load(self) -> list[dict[str, Any]]:
        """Load prior messages from the transcript.

        Returns
        -------
        list[dict[str, Any]]
            Previously persisted messages.
        """
        if not self.path.exists():
            return []
        return [
            json.loads(line) for line in self.path.read_text().splitlines()
        ]
