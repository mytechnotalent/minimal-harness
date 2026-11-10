"""Per-user interface preferences for the desktop shell."""

import json
from pathlib import Path


class Settings:
    """Persist interface toggles for the current user."""

    defaults = {
        "show_commands": False,
        "show_tools": False,
        "speak_replies": True,
        "workspace": "",
    }

    def __init__(self, path: Path | str = "runs/gui-settings.json") -> None:
        """Load settings from a JSON file.

        Parameters
        ----------
        path : pathlib.Path or str
            Settings file path.

        Returns
        -------
        None
            This initializer loads stored values.
        """
        self.path = Path(path)
        self.values: dict[str, bool | str] = dict(self.defaults)
        self._load()

    def _load(self) -> None:
        """Read stored settings values.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Stored values override defaults.
        """
        if not self.path.exists():
            return
        data = self._read_data()
        for key in self.defaults:
            if isinstance(data.get(key), (bool, str)):
                self.values[key] = data[key]

    def _read_data(self):
        """Read the stored JSON document.

        Parameters
        ----------
        None

        Returns
        -------
        object
            Parsed document, or an empty mapping when unreadable.
        """
        try:
            return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def get(self, key: str) -> bool | str:
        """Return a setting value.

        Parameters
        ----------
        key : str
            Setting name.

        Returns
        -------
        bool or str
            Stored or default value.
        """
        return self.values[key]

    def set(self, key: str, value: bool | str) -> None:
        """Store a setting value.

        Parameters
        ----------
        key : str
            Setting name.
        value : bool or str
            New value.

        Returns
        -------
        None
            The value is stored to disk.
        """
        self.values[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.values, indent=2) + "\n")
