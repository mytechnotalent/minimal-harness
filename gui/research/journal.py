"""Recoverable operation journals for research maintenance work."""

import time
from pathlib import Path

from .atomic import read_json
from .atomic import write_json_atomic


class Journal:
    """Persist the state and progress of one operation."""

    def __init__(self, path):
        """Configure a journal at one path.

        Parameters
        ----------
        path : pathlib.Path or str
            Journal file path.

        Returns
        -------
        None
            The journal object is configured.
        """
        self.path = Path(path)

    def read(self):
        """Return the current journal document.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Journal data or an empty mapping when absent.
        """
        if not self.path.exists():
            return {}
        return read_json(self.path)

    def write(self, state, **fields):
        """Merge fields into the journal and persist it.

        Parameters
        ----------
        state : str
            New operation state.
        fields : dict
            Additional journal fields.

        Returns
        -------
        dict
            Updated journal data.
        """
        data = self.read()
        data.update(fields)
        data["state"] = state
        data["updated"] = time.time()
        write_json_atomic(self.path, data)
        return data

    def remove(self):
        """Delete the journal file.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The file is removed when present.
        """
        self.path.unlink(missing_ok=True)
