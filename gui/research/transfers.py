"""Intentional cross-window transfers with provenance."""

import json
import time
from pathlib import Path

from .atomic import append_text
from .ids import new_id

TRANSFER_PREFIX = "tr"


class TransferStore:
    """Append transfer records for one primary session."""

    def __init__(self, session_folder):
        """Prepare transfer storage for a session.

        Parameters
        ----------
        session_folder : pathlib.Path or str
            Primary session folder.

        Returns
        -------
        None
            The research directory exists.
        """
        self.session_folder = Path(session_folder)
        self.session_id = self.session_folder.name
        self.root = self.session_folder / "research"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "transfers.jsonl"

    def append(
        self,
        direction,
        kind,
        text,
        source_thread_id=None,
        target_thread_id=None,
    ):
        """Record one deliberate transfer.

        Parameters
        ----------
        direction : str
            ``primary_to_research`` or ``research_to_primary``.
        kind : str
            ``message`` or ``selection``.
        text : str
            Transferred text.
        source_thread_id : str or None
            Source research thread.
        target_thread_id : str or None
            Destination research thread.

        Returns
        -------
        dict
            Transfer record.
        """
        record = _transfer_base(self.session_id, direction, kind, text)
        record.update(_thread_ids(source_thread_id, target_thread_id))
        append_text(self.path, json.dumps(record) + "\n")
        return record

    def list(self):
        """Return all transfer records in order.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Transfer records.
        """
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]


def _thread_ids(source, target):
    """Build transfer thread reference fields.

    Parameters
    ----------
    source : str or None
        Source research thread.
    target : str or None
        Destination research thread.

    Returns
    -------
    dict
        Thread reference fields.
    """
    return {"source_thread_id": source, "target_thread_id": target}


def _transfer_base(session_id, direction, kind, text):
    """Build the identity and text fields of a transfer.

    Parameters
    ----------
    session_id : str
        Owning session identifier.
    direction : str
        Transfer direction.
    kind : str
        Transfer kind.
    text : str
        Transferred text.

    Returns
    -------
    dict
        Identity and text fields.
    """
    record = _base_ids(session_id, direction, kind)
    record.update(_base_text(text))
    return record


def _base_ids(session_id, direction, kind):
    """Build transfer identity fields.

    Parameters
    ----------
    session_id : str
        Owning session identifier.
    direction : str
        Transfer direction.
    kind : str
        Transfer kind.

    Returns
    -------
    dict
        Identity fields.
    """
    return {
        "id": new_id(TRANSFER_PREFIX),
        "session_id": session_id,
        "direction": direction,
        "kind": kind,
    }


def _base_text(text):
    """Build transfer text and confirmation fields.

    Parameters
    ----------
    text : str
        Transferred text.

    Returns
    -------
    dict
        Text and confirmation fields.
    """
    return {
        "excerpt": text[:2000],
        "user_confirmed": True,
        "created_at": time.time(),
    }
