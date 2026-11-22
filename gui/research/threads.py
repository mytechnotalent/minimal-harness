"""Session-scoped research thread metadata and transcripts."""

import time
from pathlib import Path

from .atomic import read_json
from .atomic import write_json_atomic
from .ids import new_id
from .ids import require_id
from .schemas import validate_thread


class ThreadStore:
    """Manage research threads inside one primary session folder."""

    def __init__(self, session_folder):
        """Prepare the thread store for a session.

        Parameters
        ----------
        session_folder : pathlib.Path or str
            Primary session folder.

        Returns
        -------
        None
            The thread directory exists.
        """
        self.session_folder = Path(session_folder)
        self.session_id = self.session_folder.name
        self.root = self.session_folder / "research" / "threads"
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, title="Untitled research"):
        """Create one research thread with an empty transcript.

        Parameters
        ----------
        title : str
            Thread title.

        Returns
        -------
        dict
            Thread metadata.
        """
        thread_id = new_id("th")
        folder = self.root / thread_id
        folder.mkdir(parents=True, exist_ok=True)
        meta = _thread_meta(thread_id, self.session_id, title)
        self._save(meta)
        (folder / "transcript.jsonl").touch(exist_ok=True)
        return meta

    def default(self):
        """Return the newest active thread, creating one when needed.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Thread metadata.
        """
        threads = self.list()
        if threads:
            return threads[0]
        return self.create()

    def list(self, status="active"):
        """List threads filtered by status.

        Parameters
        ----------
        status : str or None
            Status filter, or ``None`` for all.

        Returns
        -------
        list
            Thread metadata records, newest first.
        """
        metas = [read_json(path) for path in self.root.glob("*/meta.json")]
        metas = [meta for meta in metas if _matches(meta, status)]
        return sorted(
            metas, key=lambda meta: meta.get("updated", 0), reverse=True
        )

    def get(self, thread_id):
        """Load one thread by identifier.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        dict
            Thread metadata.
        """
        require_id(thread_id, "th")
        return read_json(self._folder(thread_id) / "meta.json")

    def transcript_path(self, thread_id):
        """Return the transcript path for a thread.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        pathlib.Path
            JSONL transcript path.
        """
        require_id(thread_id, "th")
        return self._folder(thread_id) / "transcript.jsonl"

    def update(self, thread_id, **changes):
        """Apply supported changes to a thread.

        Parameters
        ----------
        thread_id : str
            Thread identifier.
        changes : dict
            Optional title, tags, or snapshot_enabled values.

        Returns
        -------
        dict
            Updated metadata.
        """
        meta = self.get(thread_id)
        _copy_changes(meta, changes)
        meta["updated"] = time.time()
        self._save(meta)
        return meta

    def archive(self, thread_id):
        """Hide a thread from the active list.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        dict
            Updated metadata.
        """
        return self._set_status(thread_id, "archived")

    def restore(self, thread_id):
        """Return an archived thread to the active list.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        dict
            Updated metadata.
        """
        return self._set_status(thread_id, "active")

    def _set_status(self, thread_id, status):
        """Set a thread status and archive timestamp.

        Parameters
        ----------
        thread_id : str
            Thread identifier.
        status : str
            New status.

        Returns
        -------
        dict
            Updated metadata.
        """
        meta = self.get(thread_id)
        meta["status"] = status
        meta["archived_at"] = time.time() if status == "archived" else None
        meta["updated"] = time.time()
        self._save(meta)
        return meta

    def _save(self, meta):
        """Validate and persist one thread record.

        Parameters
        ----------
        meta : dict
            Thread metadata.

        Returns
        -------
        None
            The metadata is written atomically.
        """
        validate_thread(meta)
        write_json_atomic(self._folder(meta["id"]) / "meta.json", meta)

    def _folder(self, thread_id):
        """Return the folder for a thread.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        pathlib.Path
            Thread folder.
        """
        return self.root / thread_id


def _thread_meta(thread_id, session_id, title):
    """Build new thread metadata.

    Parameters
    ----------
    thread_id : str
        Thread identifier.
    session_id : str
        Owning session identifier.
    title : str
        Thread title.

    Returns
    -------
    dict
        Thread metadata.
    """
    now = time.time()
    meta = {"id": thread_id, "session_id": session_id, "title": title}
    meta.update(_thread_state(now))
    return meta


def _thread_state(now):
    """Build default thread state fields.

    Parameters
    ----------
    now : float
        Creation timestamp.

    Returns
    -------
    dict
        State fields.
    """
    meta = {"tags": [], "status": "active", "snapshot_enabled": False}
    meta.update({"created": now, "updated": now})
    meta["archived_at"] = None
    meta["message_count"] = 0
    return meta


def _copy_changes(meta, changes):
    """Copy supported change keys into thread metadata.

    Parameters
    ----------
    meta : dict
        Thread metadata.
    changes : dict
        Requested changes.

    Returns
    -------
    None
        Supported values are copied.
    """
    for key in ("title", "tags", "snapshot_enabled"):
        if key in changes:
            meta[key] = changes[key]


def _matches(meta, status):
    """Return whether a thread matches a status filter.

    Parameters
    ----------
    meta : dict
        Thread metadata.
    status : str or None
        Status filter.

    Returns
    -------
    bool
        ``True`` when the thread matches.
    """
    return status is None or meta.get("status") == status
