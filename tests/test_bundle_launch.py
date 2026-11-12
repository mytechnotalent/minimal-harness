"""Offline tests for macOS bundle re-launching."""

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from gui import app as gui_app
except Exception:
    gui_app = None


@unittest.skipUnless(gui_app is not None, "PySide6 is not installed")
class BundleLaunchTests(unittest.TestCase):
    """Verify the console launcher targets the installed bundle."""

    def test_console_scripts_are_launchers(self) -> None:
        """The harness-gui and harness-voice scripts relaunch.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with mock.patch.object(gui_app.sys, "argv", ["harness-gui"]):
            self.assertTrue(gui_app._is_bundle_launcher())
        with mock.patch.object(gui_app.sys, "argv", ["harness-voice"]):
            self.assertTrue(gui_app._is_bundle_launcher())

    def test_other_processes_are_not_launchers(self) -> None:
        """The bundle executable and module entry points do not relaunch.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with mock.patch.object(gui_app.sys, "argv", ["Minimal Harness"]):
            self.assertFalse(gui_app._is_bundle_launcher())
        with mock.patch.object(gui_app.sys, "argv", ["gui/app.py"]):
            self.assertFalse(gui_app._is_bundle_launcher())

    def test_bundle_executable_is_none_off_macos(self) -> None:
        """Non-macOS platforms skip the bundle lookup.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with mock.patch.object(gui_app.sys, "platform", "linux"):
            self.assertIsNone(gui_app._bundle_executable())

    def test_bundle_matches_current_repository(self) -> None:
        """A bundle pointing at this checkout is accepted.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        root = Path(gui_app.__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            contents = app / "Contents"
            contents.mkdir()
            _write_plist(contents / "Info.plist", str(root))
            self.assertTrue(gui_app._bundle_matches(app))

    def test_bundle_rejects_another_repository(self) -> None:
        """A bundle built from elsewhere is rejected.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            contents = app / "Contents"
            contents.mkdir()
            _write_plist(contents / "Info.plist", "/tmp/other-repo")
            self.assertFalse(gui_app._bundle_matches(app))

    @mock.patch("gui.app.subprocess.Popen")
    @mock.patch(
        "gui.app._bundle_executable", new=mock.Mock(return_value=Path("/b"))
    )
    @mock.patch("gui.app.os.getenv", new=mock.Mock(return_value=None))
    @mock.patch("gui.app.sys.argv", new=["harness-gui"])
    def test_launch_bundle_spawns_detached_process(self, popen) -> None:
        """A launcher starts the bundle and returns without waiting.

        Parameters
        ----------
        popen : unittest.mock.Mock
            Patched ``subprocess.Popen``.

        Returns
        -------
        None
        """
        self.assertTrue(gui_app._launch_bundle())
        popen.assert_called_once()
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_launch_bundle_skips_guarded_child(self) -> None:
        """A bundle child does not spawn another launch.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with mock.patch.object(gui_app.sys, "argv", ["harness-gui"]):
            with mock.patch.object(gui_app.os, "getenv", return_value="1"):
                self.assertFalse(gui_app._launch_bundle())


def _write_plist(path: Path, home: str) -> None:
    """Write a minimal Info.plist with an HARNESS_HOME value.

    Parameters
    ----------
    path : pathlib.Path
        Destination plist path.
    home : str
        Configured repository root.

    Returns
    -------
    None
        The plist is written.
    """
    data = {"LSEnvironment": {"HARNESS_HOME": home}}
    path.write_bytes(plistlib.dumps(data))
