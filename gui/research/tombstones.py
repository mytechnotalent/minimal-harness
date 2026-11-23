"""Thread tombstones that keep deleted thread provenance."""

import time
from pathlib import Path

from .atomic import write_json_atomic


def write_thread_tombstone(
    research_root,
    thread,
    note_ids=(),
    source_ids=(),
    evidence_ids=(),
    transfer_ids=(),
):
    """Write a tombstone for a deleted research thread.

    Parameters
    ----------
    research_root : pathlib.Path or str
        Global research data root.
    thread : dict
        Thread metadata before deletion.
    note_ids : collections.abc.Iterable
        Surviving note identifiers.
    source_ids : collections.abc.Iterable
        Surviving source identifiers.
    evidence_ids : collections.abc.Iterable
        Surviving evidence identifiers.
    transfer_ids : collections.abc.Iterable
        Related transfer identifiers.

    Returns
    -------
    dict
        Written tombstone record.
    """
    record = _tombstone(
        thread, note_ids, source_ids, evidence_ids, transfer_ids
    )
    path = Path(research_root) / "tombstones" / "threads"
    write_json_atomic(path / f"{thread['id']}.json", record)
    return record


def _tombstone(thread, note_ids, source_ids, evidence_ids, transfer_ids):
    """Build a thread tombstone record.

    Parameters
    ----------
    thread : dict
        Thread metadata.
    note_ids : collections.abc.Iterable
        Surviving note identifiers.
    source_ids : collections.abc.Iterable
        Surviving source identifiers.
    evidence_ids : collections.abc.Iterable
        Surviving evidence identifiers.
    transfer_ids : collections.abc.Iterable
        Related transfer identifiers.

    Returns
    -------
    dict
        Tombstone record.
    """
    record = _tombstone_base(thread)
    record.update(
        _tombstone_links(note_ids, source_ids, evidence_ids, transfer_ids)
    )
    return record


def _tombstone_base(thread):
    """Build the identity fields of a tombstone.

    Parameters
    ----------
    thread : dict
        Thread metadata.

    Returns
    -------
    dict
        Identity fields.
    """
    return {
        "thread_id": thread["id"],
        "session_id": thread["session_id"],
        "title": thread.get("title", ""),
        "created": thread.get("created", 0),
        "deleted": time.time(),
        "message_count": thread.get("message_count", 0),
    }


def _tombstone_links(note_ids, source_ids, evidence_ids, transfer_ids):
    """Build the surviving record links of a tombstone.

    Parameters
    ----------
    note_ids : collections.abc.Iterable
        Surviving note identifiers.
    source_ids : collections.abc.Iterable
        Surviving source identifiers.
    evidence_ids : collections.abc.Iterable
        Surviving evidence identifiers.
    transfer_ids : collections.abc.Iterable
        Related transfer identifiers.

    Returns
    -------
    dict
        Link fields.
    """
    return {
        "note_ids": list(note_ids),
        "source_ids": list(source_ids),
        "evidence_ids": list(evidence_ids),
        "transfer_ids": list(transfer_ids),
    }
