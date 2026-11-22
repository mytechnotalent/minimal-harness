"""Persistent global note store with revisions and scope filters."""

import copy
import shutil
import time
from pathlib import Path

from .atomic import read_json
from .atomic import write_json_atomic
from .ids import new_id
from .ids import require_id
from .schemas import validate_note

NOTE_PREFIX = "nt"


class NoteStore:
    """Store notes and immutable revisions outside thread folders."""

    def __init__(self, root):
        """Prepare the note store at a research root.

        Parameters
        ----------
        root : pathlib.Path or str
            Research data root.

        Returns
        -------
        None
            The note and revision directories exist.
        """
        self.root = Path(root)
        self.notes = self.root / "notes"
        self.revision_root = self.notes / "revisions"
        self.notes.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        scope,
        title,
        body_md,
        origin,
        tags=None,
        source_ids=None,
        evidence_ids=None,
        kind="note",
    ):
        """Create and persist a new note.

        Parameters
        ----------
        scope : dict
            Session and thread scope.
        title : str
            Note title.
        body_md : str
            Markdown body.
        origin : dict
            Immutable origin snapshot.
        tags : list or None
            Optional tags.
        source_ids : list or None
            Referenced source identifiers.
        evidence_ids : list or None
            Referenced evidence identifiers.
        kind : str
            Note kind, normally ``note`` or ``summary``.

        Returns
        -------
        dict
            Persisted note record.
        """
        note = _new_note(
            scope, title, body_md, origin, tags, source_ids, evidence_ids, kind
        )
        self.save(note)
        return note

    def save(self, note):
        """Validate and write one note record.

        Parameters
        ----------
        note : dict
            Note record.

        Returns
        -------
        None
            The note is written atomically.
        """
        validate_note(note)
        write_json_atomic(self._path(note["id"]), note)

    def get(self, note_id):
        """Load one note by identifier.

        Parameters
        ----------
        note_id : str
            Note identifier.

        Returns
        -------
        dict
            Note record.
        """
        require_id(note_id, NOTE_PREFIX)
        return read_json(self._path(note_id))

    def list(self, session_id=None, thread_id=None, status="active"):
        """List notes filtered by scope and status.

        Parameters
        ----------
        session_id : str or None
            Optional session scope.
        thread_id : str or None
            Optional thread scope.
        status : str or None
            Optional status filter, or ``None`` for all.

        Returns
        -------
        list
            Matching note records.
        """
        notes = [read_json(path) for path in self._paths()]
        return [n for n in notes if _matches(n, session_id, thread_id, status)]

    def update(self, note_id, editor="user", **changes):
        """Apply changes and store the previous version as a revision.

        Parameters
        ----------
        note_id : str
            Note identifier.
        editor : str
            Editor label.
        changes : dict
            Optional title, body_md, or tags.

        Returns
        -------
        dict
            Updated note record.
        """
        note = self.get(note_id)
        self._write_revision(note, editor)
        updated = _updated_note(note, changes)
        self.save(updated)
        return updated

    def restore_revision(self, note_id, revision, editor="user"):
        """Restore an earlier revision as a new current revision.

        Parameters
        ----------
        note_id : str
            Note identifier.
        revision : int
            Revision number to restore.
        editor : str
            Editor label.

        Returns
        -------
        dict
            Updated note record.
        """
        note = self.get(note_id)
        target = self._read_revision(note_id, revision)
        self._write_revision(note, editor)
        restored = _restored_note(note, target)
        self.save(restored)
        return restored

    def revisions(self, note_id):
        """Return every stored revision for a note.

        Parameters
        ----------
        note_id : str
            Note identifier.

        Returns
        -------
        list
            Revision records ordered by revision number.
        """
        require_id(note_id, NOTE_PREFIX)
        folder = self.revision_root / note_id
        return [read_json(path) for path in sorted(folder.glob("r*.json"))]

    def delete(self, note_id):
        """Delete a note and all of its revisions.

        Parameters
        ----------
        note_id : str
            Note identifier.

        Returns
        -------
        None
            The note is removed.
        """
        require_id(note_id, NOTE_PREFIX)
        self._path(note_id).unlink(missing_ok=True)
        shutil.rmtree(self.revision_root / note_id, ignore_errors=True)

    def _paths(self):
        """Return note file paths in sorted order.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Note JSON paths.
        """
        return sorted(self.notes.glob("nt_*.json"))

    def _path(self, note_id):
        """Return the current note file path.

        Parameters
        ----------
        note_id : str
            Note identifier.

        Returns
        -------
        pathlib.Path
            Note JSON path.
        """
        return self.notes / f"{note_id}.json"

    def _write_revision(self, note, editor):
        """Store the current note state as an immutable revision.

        Parameters
        ----------
        note : dict
            Current note record.
        editor : str
            Editor label for the new version.

        Returns
        -------
        None
            The revision is written.
        """
        record = _revision_from(note, editor)
        write_json_atomic(
            self._revision_path(note["id"], note["revision"]), record
        )

    def _read_revision(self, note_id, revision):
        """Load one revision record.

        Parameters
        ----------
        note_id : str
            Note identifier.
        revision : int
            Revision number.

        Returns
        -------
        dict
            Revision record.
        """
        require_id(note_id, NOTE_PREFIX)
        return read_json(self._revision_path(note_id, revision))

    def _revision_path(self, note_id, revision):
        """Return a revision file path.

        Parameters
        ----------
        note_id : str
            Note identifier.
        revision : int
            Revision number.

        Returns
        -------
        pathlib.Path
            Revision JSON path.
        """
        number = int(revision)
        if number < 1:
            raise ValueError("revision must be positive")
        return self.revision_root / note_id / f"r{number:04d}.json"


def _new_note(
    scope,
    title,
    body_md,
    origin,
    tags,
    source_ids,
    evidence_ids,
    kind,
):
    """Build a new note record.

    Parameters
    ----------
    scope : dict
        Session and thread scope.
    title : str
        Note title.
    body_md : str
        Markdown body.
    origin : dict
        Immutable origin snapshot.
    tags : list or None
        Optional tags.
    source_ids : list or None
        Referenced source identifiers.
    evidence_ids : list or None
        Referenced evidence identifiers.
    kind : str
        Note kind.

    Returns
    -------
    dict
        New note record.
    """
    now = time.time()
    record = _note_core(scope, title, body_md, origin, kind, now)
    record["tags"] = list(tags or [])
    record["source_ids"] = list(source_ids or [])
    record["evidence_ids"] = list(evidence_ids or [])
    return record


def _note_core(scope, title, body_md, origin, kind, now):
    """Build the identity, body, and date fields of a note.

    Parameters
    ----------
    scope : dict
        Session and thread scope.
    title : str
        Note title.
    body_md : str
        Markdown body.
    origin : dict
        Immutable origin snapshot.
    kind : str
        Note kind.
    now : float
        Creation timestamp.

    Returns
    -------
    dict
        Partial note record.
    """
    record = {"id": new_id(NOTE_PREFIX), "kind": kind, "scope": dict(scope)}
    record.update(_note_body(title, body_md, origin))
    record.update(_note_dates(now))
    return record


def _note_body(title, body_md, origin):
    """Build note text fields.

    Parameters
    ----------
    title : str
        Note title.
    body_md : str
        Markdown body.
    origin : dict
        Immutable origin snapshot.

    Returns
    -------
    dict
        Text fields.
    """
    return {"title": title, "body_md": body_md, "origin": dict(origin)}


def _note_dates(now):
    """Build initial note state and timestamps.

    Parameters
    ----------
    now : float
        Creation timestamp.

    Returns
    -------
    dict
        State fields.
    """
    return {
        "status": "active",
        "revision": 1,
        "created": now,
        "updated": now,
        "restored_from_revision": None,
        "restored": None,
    }


def _updated_note(note, changes):
    """Return a copy of a note with approved changes applied.

    Parameters
    ----------
    note : dict
        Current note.
    changes : dict
        Requested changes.

    Returns
    -------
    dict
        Updated note.
    """
    updated = copy.deepcopy(note)
    _copy_changes(updated, changes)
    updated["revision"] += 1
    updated["updated"] = time.time()
    return updated


def _copy_changes(record, changes):
    """Copy supported change keys into a record.

    Parameters
    ----------
    record : dict
        Destination record.
    changes : dict
        Requested changes.

    Returns
    -------
    None
        Supported values are copied.
    """
    for key in ("title", "body_md", "tags"):
        if key in changes:
            record[key] = copy.deepcopy(changes[key])


def _restored_note(note, target):
    """Return a note whose body comes from an earlier revision.

    Parameters
    ----------
    note : dict
        Current note.
    target : dict
        Revision to restore.

    Returns
    -------
    dict
        Restored note.
    """
    updated = copy.deepcopy(note)
    updated["title"] = target["title"]
    updated["body_md"] = target["body_md"]
    updated["revision"] += 1
    updated["updated"] = time.time()
    updated["restored_from_revision"] = target["revision"]
    return updated


def _revision_from(note, editor):
    """Build a revision record from a note.

    Parameters
    ----------
    note : dict
        Note being superseded.
    editor : str
        Editor label.

    Returns
    -------
    dict
        Revision record.
    """
    record = _revision_ids(note)
    record.update(_revision_text(note, editor))
    return record


def _revision_ids(note):
    """Build the identity and timestamps of a revision.

    Parameters
    ----------
    note : dict
        Note being superseded.

    Returns
    -------
    dict
        Identity fields.
    """
    return {
        "note_id": note["id"],
        "revision": note["revision"],
        "created": note["created"],
    }


def _revision_text(note, editor):
    """Build the text fields of a revision.

    Parameters
    ----------
    note : dict
        Note being superseded.
    editor : str
        Editor label.

    Returns
    -------
    dict
        Text fields.
    """
    return {
        "title": note["title"],
        "body_md": note["body_md"],
        "saved_at": note["updated"],
        "editor": editor,
        "restored_from_revision": None,
    }


def _matches(note, session_id, thread_id, status):
    """Return whether a note passes scope and status filters.

    Parameters
    ----------
    note : dict
        Note record.
    session_id : str or None
        Session filter.
    thread_id : str or None
        Thread filter.
    status : str or None
        Status filter.

    Returns
    -------
    bool
        ``True`` when the note matches.
    """
    scope = note.get("scope", {})
    if session_id is not None and scope.get("session_id") != session_id:
        return False
    if thread_id is not None and scope.get("thread_id") != thread_id:
        return False
    return status is None or note.get("status") == status
