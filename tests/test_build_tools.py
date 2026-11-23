"""Offline tests for the desktop launcher script."""

import unittest
from unittest.mock import patch

try:
    from scripts import run_desktop
except ImportError:
    run_desktop = None


@unittest.skipUnless(run_desktop is not None, "PySide6 is not installed")
class RunDesktopTests(unittest.TestCase):
    """Verify the bundle launcher switches to the harness home."""

    def test_main_chdirs_and_launches(self) -> None:
        """The launcher uses HARNESS_HOME and calls gui.app.main.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        home = "/tmp/harness"
        with patch.dict("os.environ", {"HARNESS_HOME": home}):
            with patch.object(run_desktop.os, "chdir") as chdir:
                with patch.object(run_desktop.gui.app, "main") as launch:
                    run_desktop.main()
        chdir.assert_called_once_with(home)
        launch.assert_called_once_with()

    def test_main_launches_without_home(self) -> None:
        """The launcher skips chdir when HARNESS_HOME is unset.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(run_desktop.os, "chdir") as chdir:
                with patch.object(run_desktop.gui.app, "main") as launch:
                    run_desktop.main()
        chdir.assert_not_called()
        launch.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
