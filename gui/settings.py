"""Per-user interface preferences for the desktop shell."""

import json
from pathlib import Path


class Settings:
    """Persist interface toggles for the current user."""

    defaults = {
        "show_commands": False,
        "show_tools": False,
        "speak_replies": True,
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
        self.values: dict[str, bool] = dict(self.defaults)
        self._load()

    def _load(self) -> None:
        """Read stored settings values.

        Returns
        -------
        None
            Stored values override defaults.
        """
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for key in self.defaults:
            if isinstance(data.get(key), bool):
                self.values[key] = data[key]

    def get(self, key: str) -> bool:
        """Return a setting value.

        Parameters
        ----------
        key : str
            Setting name.

        Returns
        -------
        bool
            Stored or default value.
        """
        return self.values[key]

    def set(self, key: str, value: bool) -> None:
        """Store a setting value.

        Parameters
        ----------
        key : str
            Setting name.
        value : bool
            New value.

        Returns
        -------
        None
            The value is stored to disk.
        """
        self.values[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.values, indent=2) + "\n")
