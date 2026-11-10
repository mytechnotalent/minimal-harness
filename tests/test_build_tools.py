"""Offline tests for the macOS build and launcher scripts."""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from scripts import build_macos_app
from scripts import run_desktop

ROOT = Path(__file__).resolve().parent.parent


class BuildMacosAppTests(unittest.TestCase):
    """Verify bundle build and install helpers."""

    def test_build_runs_py2app(self) -> None:
        """The build uses the venv Python and setup_app.py.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(build_macos_app.subprocess, "run") as run:
                build_macos_app._build(root)
        args, kwargs = _build_call(root)
        run.assert_called_once_with(args, **kwargs)

    def test_install_replaces_existing_bundle(self) -> None:
        """Installing removes the old bundle and copies the new one.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = _old_bundle(root)
            with patch("pathlib.Path.home", return_value=home):
                target = build_macos_app._install(root)
            self.assertFalse((target / "old.txt").exists())
            self.assertTrue((target / "Contents" / "new.txt").exists())

    def test_install_preserves_symlinks(self) -> None:
        """Installing keeps alias-mode symlinks instead of following them.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root = _alias_bundle(Path(directory))
            with patch("pathlib.Path.home", return_value=root / "home"):
                target = build_macos_app._install(root)
            self.assertTrue((target / "Contents" / "dangling").is_symlink())

    def test_main_rejects_non_macos(self) -> None:
        """Non-macOS platforms return an error.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.object(build_macos_app.sys, "platform", "linux"):
            with patch("builtins.print"):
                self.assertEqual(build_macos_app.main(), 1)

    @patch("builtins.print")
    @patch.object(build_macos_app, "_install")
    @patch.object(build_macos_app, "_build")
    @patch.object(build_macos_app.sys, "platform", "darwin")
    def test_main_builds_and_installs(self, build, install, printer) -> None:
        """The macOS path builds, installs, and prints the target.

        Parameters
        ----------
        build : unittest.mock.Mock
            Patched bundle builder.

        install : unittest.mock.Mock
            Patched bundle installer.

        printer : unittest.mock.Mock
            Patched print function.

        Returns
        -------
        None
        """
        target = Path("/tmp/Minimal Harness.app")
        install.return_value = target
        self.assertEqual(build_macos_app.main(), 0)
        build.assert_called_once()
        install.assert_called_once()
        printer.assert_called_once_with(target)


class RunDesktopTests(unittest.TestCase):
    """Verify the bundle launcher switches to the repository."""

    def test_main_chdirs_and_launches(self) -> None:
        """The launcher uses HARNESS_HOME and calls gui.app.main.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        called = []
        home = str(Path("/tmp/harness"))
        chdir = self._run_main(home, called)
        self.assertEqual(sys.path[0], home)
        sys.path.remove(home)
        chdir.assert_called_once_with(Path("/tmp/harness"))
        self.assertEqual(called, [True])

    def _run_main(self, home, called):
        """Run the launcher with fake gui modules.

        Parameters
        ----------
        home : str
            Fake HARNESS_HOME value.

        called : list
            List appended to when gui.app.main runs.

        Returns
        -------
        unittest.mock.Mock
            Patched chdir mock.
        """
        with patch.dict(sys.modules, _fake_gui(called)):
            with patch.dict("os.environ", {"HARNESS_HOME": home}):
                with patch.object(run_desktop.os, "chdir") as chdir:
                    run_desktop.main()
        return chdir


class SetupAppTests(unittest.TestCase):
    """Verify the py2app setup configuration."""

    def test_setup_uses_minimal_harness_identity(self) -> None:
        """The setup passes the app name, alias, and bundle id.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        kwargs = _setup_kwargs()
        self._assert_identity(kwargs)

    def _assert_identity(self, kwargs) -> None:
        """Verify the bundle name, alias mode, and identifier.

        Parameters
        ----------
        kwargs : dict
            Captured py2app setup keyword arguments.

        Returns
        -------
        None
            Assertions document the configuration.
        """
        self.assertEqual(kwargs["name"], "Minimal Harness")
        self.assertTrue(kwargs["options"]["py2app"]["alias"])
        plist = kwargs["options"]["py2app"]["plist"]
        self.assertEqual(
            plist["CFBundleIdentifier"], "com.minimalharness.desktop"
        )


def _alias_bundle(root: Path) -> Path:
    """Create a fake alias bundle with a dangling symlink.

    Parameters
    ----------
    root : pathlib.Path
        Temporary repository root.

    Returns
    -------
    pathlib.Path
        Repository root containing the fake bundle.
    """
    source = root / "dist" / "Minimal Harness.app"
    contents = source / "Contents"
    contents.mkdir(parents=True)
    (contents / "dangling").symlink_to("/missing/target")
    return root


if __name__ == "__main__":
    unittest.main()


def _build_call(root: Path) -> tuple:
    """Build the expected py2app call arguments.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    tuple
        Positional and keyword arguments for the run call.
    """
    python = root / ".venv" / "bin" / "python"
    args = [str(python), "setup_app.py", "py2app", "-A"]
    kwargs = {"cwd": root, "check": True}
    return args, kwargs


def _old_bundle(root: Path) -> Path:
    """Create a new bundle and an old installed bundle.

    Parameters
    ----------
    root : pathlib.Path
        Temporary repository root.

    Returns
    -------
    pathlib.Path
        Fake home directory holding the old bundle.
    """
    source = root / "dist" / "Minimal Harness.app"
    (source / "Contents").mkdir(parents=True)
    (source / "Contents" / "new.txt").write_text("new")
    home = root / "home"
    old = home / "Applications" / "Minimal Harness.app"
    old.mkdir(parents=True)
    (old / "old.txt").write_text("old")
    return home


def _fake_gui(called: list) -> dict:
    """Build fake gui modules that record a launch.

    Parameters
    ----------
    called : list
        List appended to when gui.app.main runs.

    Returns
    -------
    dict
        Module mapping for ``sys.modules``.
    """
    package = types.ModuleType("gui")
    package.__path__ = []
    app = types.ModuleType("gui.app")
    app.main = lambda: called.append(True)
    return {"gui": package, "gui.app": app}


def _setup_kwargs() -> dict:
    """Load setup_app.py with a mocked setuptools and return its options.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Keyword arguments passed to setuptools.setup.
    """
    spec = _setup_spec()
    module = importlib.util.module_from_spec(spec)
    fake = types.ModuleType("setuptools")
    fake.setup = Mock()
    with patch.dict(sys.modules, {"setuptools": fake}):
        spec.loader.exec_module(module)
    return fake.setup.call_args.kwargs


def _setup_spec():
    """Return the setup_app module spec.

    Parameters
    ----------
    None

    Returns
    -------
    importlib.machinery.ModuleSpec
        Spec for setup_app.py.
    """
    return importlib.util.spec_from_file_location(
        "setup_app", ROOT / "setup_app.py"
    )


if __name__ == "__main__":
    unittest.main()
