"""Read-only restored primary history stored with a session."""

import json
from pathlib import Path

from .atomic import read_json
from .ids import require_id


class RestoredHistoryStore:
    """List and read restored primary transcripts for one session."""

    def __init__(self, session_folder):
        """Prepare the store for a session.

        Parameters
        ----------
        session_folder : pathlib.Path or str
            Primary session folder.

        Returns
        -------
        None
            The restored history directory exists.
        """
        self.session_folder = Path(session_folder)
        self.root = self.session_folder / "restored"
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self):
        """Return restored history metadata, newest first.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Restored history records.
        """
        metas = [read_json(path) for path in self.root.glob("*/meta.json")]
        return sorted(
            metas,
            key=lambda meta: meta.get("restored_at", 0),
            reverse=True,
        )

    def get(self, history_id):
        """Load one restored history record.

        Parameters
        ----------
        history_id : str
            Restored history identifier.

        Returns
        -------
        dict
            Restored history metadata.
        """
        require_id(history_id, "rh")
        return read_json(self._folder(history_id) / "meta.json")

    def transcript(self, history_id):
        """Read a restored primary transcript.

        Parameters
        ----------
        history_id : str
            Restored history identifier.

        Returns
        -------
        list
            Transcript messages.
        """
        require_id(history_id, "rh")
        path = self._folder(history_id) / "transcript.jsonl"
        return [_line(line) for line in path.read_text().splitlines() if line]

    def _folder(self, history_id):
        """Return the folder for a restored history.

        Parameters
        ----------
        history_id : str
            Restored history identifier.

        Returns
        -------
        pathlib.Path
            Restored history folder.
        """
        return self.root / history_id


def _line(text):
    """Parse one JSONL transcript line.

    Parameters
    ----------
    text : str
        Raw JSON line.

    Returns
    -------
    dict
        Parsed message.
    """
    return json.loads(text)
