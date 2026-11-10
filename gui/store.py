"""Persistent session store for named build sessions."""

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SessionRecord:
    """Describe one saved session folder."""

    session_id: str
    folder: Path
    title: str
    kind: str
    transcript: Path
    notes: Path
    meta: Path


def _session_meta(session_id: str, title: str, kind: str) -> dict:
    """Build the metadata document for a new session.

    Parameters
    ----------
    session_id : str
        New session identifier.

    title : str
        Optional session title.

    kind : str
        Item kind ("session" or "build").

    Returns
    -------
    dict
        Metadata ready to serialize.
    """
    now = time.time()
    return {
        "id": session_id,
        "title": title or "Untitled session",
        "kind": kind,
        "created": now,
        "updated": now,
    }


def _record_fields(folder: Path, meta: dict) -> dict:
    """Build the session record keyword arguments.

    Parameters
    ----------
    folder : pathlib.Path
        Session folder.

    meta : dict
        Parsed metadata document.

    Returns
    -------
    dict
        Keyword arguments for ``SessionRecord``.
    """
    return {
        "session_id": folder.name,
        "folder": folder,
        "title": meta.get("title", folder.name),
        "kind": meta.get("kind", "session"),
        **_record_paths(folder),
    }


def _record_paths(folder: Path) -> dict:
    """Build the session file paths.

    Parameters
    ----------
    folder : pathlib.Path
        Session folder.

    Returns
    -------
    dict
        Transcript, notes, and metadata paths.
    """
    return {
        "transcript": folder / "transcript.jsonl",
        "notes": folder / "notes.jsonl",
        "meta": folder / "meta.json",
    }


def _record(folder: Path, meta: dict) -> SessionRecord:
    """Build a session record from a folder and its metadata.

    Parameters
    ----------
    folder : pathlib.Path
        Session folder.

    meta : dict
        Parsed metadata document.

    Returns
    -------
    SessionRecord
        Session description.
    """
    return SessionRecord(**_record_fields(folder, meta))


class SessionStore:
    """Manage session folders with transcripts and notes."""

    def __init__(self, root: Path | str = "runs/sessions") -> None:
        """Prepare the store at a root directory.

        Parameters
        ----------
        root : pathlib.Path or str
            Directory holding session folders.

        Returns
        -------
        None
            The store is ready to use.
        """
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self, kind: str | None = None) -> list[SessionRecord]:
        """Return saved sessions, newest first.

        Parameters
        ----------
        kind : str or None
            Optional kind filter ("session" or "build").

        Returns
        -------
        list[SessionRecord]
            Sorted session descriptions.
        """
        records = [self._read_folder(p) for p in self.root.iterdir()]
        if kind is not None:
            records = [r for r in records if r.kind == kind]
        records.sort(key=lambda r: self._meta_time(r.meta), reverse=True)
        return records

    def create(self, title: str = "", kind: str = "session") -> SessionRecord:
        """Create a new empty session folder.

        Parameters
        ----------
        title : str
            Optional session title.
        kind : str
            Item kind ("session" or "build").

        Returns
        -------
        SessionRecord
            The new session description.
        """
        session_id = uuid.uuid4().hex[:12]
        folder = self.root / session_id
        folder.mkdir(parents=True, exist_ok=True)
        meta = _session_meta(session_id, title, kind)
        (folder / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
        return self._read_folder(folder)

    def rename(self, record: SessionRecord, title: str) -> SessionRecord:
        """Set a session title and touch its timestamp.

        Parameters
        ----------
        record : SessionRecord
            Session to update.
        title : str
            New display title.

        Returns
        -------
        SessionRecord
            Refreshed session description.
        """
        meta = json.loads(record.meta.read_text())
        meta["title"] = title
        meta["updated"] = time.time()
        record.meta.write_text(json.dumps(meta, indent=2) + "\n")
        return self._read_folder(record.folder)

    def touch(self, record: SessionRecord) -> SessionRecord:
        """Mark a session as recently used.

        Parameters
        ----------
        record : SessionRecord
            Session to bump.

        Returns
        -------
        SessionRecord
            Refreshed session description.
        """
        return self.rename(record, record.title)

    def load(self, session_id: str) -> SessionRecord:
        """Load a session by identifier.

        Parameters
        ----------
        session_id : str
            Session folder name.

        Returns
        -------
        SessionRecord
            The requested session description.
        """
        return self._read_folder(self.root / session_id)

    def _read_folder(self, folder: Path) -> SessionRecord:
        """Read one session folder into a description.

        Parameters
        ----------
        folder : pathlib.Path
            Session folder to inspect.

        Returns
        -------
        SessionRecord
            Parsed session description.
        """
        meta = self._read_meta(folder)
        return _record(folder, meta)

    def _read_meta(self, folder: Path) -> dict:
        """Read a session meta file safely.

        Parameters
        ----------
        folder : pathlib.Path
            Session folder.

        Returns
        -------
        dict
            Metadata dictionary.
        """
        path = folder / "meta.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def _meta_time(self, meta: Path) -> float:
        """Return a meta file updated timestamp.

        Parameters
        ----------
        meta : pathlib.Path
            Meta file path.

        Returns
        -------
        float
            Updated epoch or zero.
        """
        try:
            data = json.loads(meta.read_text())
        except (OSError, json.JSONDecodeError):
            return 0.0
        return float(data.get("updated", 0))
