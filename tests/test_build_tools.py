"""Offline tests for the macOS build and launcher scripts."""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import build_macos_app, run_desktop

ROOT = Path(__file__).resolve().parent.parent


class BuildMacosAppTests(unittest.TestCase):
    """Verify bundle build and install helpers."""

    def test_build_runs_py2app(self) -> None:
        """The build uses the venv Python and setup_app.py."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(build_macos_app.subprocess, "run") as run:
                build_macos_app._build(root)
        python = root / ".venv" / "bin" / "python"
        run.assert_called_once_with(
            [str(python), "setup_app.py", "py2app", "-A"],
            cwd=root,
            check=True,
        )

    def test_install_replaces_existing_bundle(self) -> None:
        """Installing removes the old bundle and copies the new one."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dist" / "Minimal Harness.app"
            (source / "Contents").mkdir(parents=True)
            (source / "Contents" / "new.txt").write_text("new")
            home = root / "home"
            old = home / "Applications" / "Minimal Harness.app"
            old.mkdir(parents=True)
            (old / "old.txt").write_text("old")
            with patch("pathlib.Path.home", return_value=home):
                target = build_macos_app._install(root)
            self.assertFalse((target / "old.txt").exists())
            self.assertTrue((target / "Contents" / "new.txt").exists())

    def test_main_rejects_non_macos(self) -> None:
        """Non-macOS platforms return an error."""
        with patch.object(build_macos_app.sys, "platform", "linux"):
            with patch("builtins.print"):
                self.assertEqual(build_macos_app.main(), 1)

    def test_main_builds_and_installs(self) -> None:
        """The macOS path builds, installs, and prints the target."""
        target = Path("/tmp/Minimal Harness.app")
        with patch.object(build_macos_app.sys, "platform", "darwin"):
            with patch.object(build_macos_app, "_build") as build:
                with patch.object(
                    build_macos_app, "_install", return_value=target
                ) as install:
                    with patch("builtins.print") as printer:
                        self.assertEqual(build_macos_app.main(), 0)
        build.assert_called_once()
        install.assert_called_once()
        printer.assert_called_once_with(target)


class RunDesktopTests(unittest.TestCase):
    """Verify the bundle launcher switches to the repository."""

    def test_main_chdirs_and_launches(self) -> None:
        """The launcher uses HARNESS_HOME and calls gui.app.main."""
        called = []
        package = types.ModuleType("gui")
        package.__path__ = []
        app = types.ModuleType("gui.app")
        app.main = lambda: called.append(True)
        with patch.dict(sys.modules, {"gui": package, "gui.app": app}):
            with patch.dict(
                "os.environ", {"HARNESS_HOME": "/tmp/harness"}, clear=False
            ):
                with patch.object(run_desktop.os, "chdir") as chdir:
                    run_desktop.main()
        chdir.assert_called_once_with(Path("/tmp/harness"))
        self.assertEqual(called, [True])


class SetupAppTests(unittest.TestCase):
    """Verify the py2app setup configuration."""

    def test_setup_uses_minimal_harness_identity(self) -> None:
        """The setup passes the app name, alias, and bundle id."""
        spec = importlib.util.spec_from_file_location(
            "setup_app", ROOT / "setup_app.py"
        )
        module = importlib.util.module_from_spec(spec)
        fake_setuptools = types.ModuleType("setuptools")
        fake_setuptools.setup = Mock()
        with patch.dict(sys.modules, {"setuptools": fake_setuptools}):
            spec.loader.exec_module(module)
        kwargs = fake_setuptools.setup.call_args.kwargs
        self.assertEqual(kwargs["name"], "Minimal Harness")
        self.assertTrue(kwargs["options"]["py2app"]["alias"])
        plist = kwargs["options"]["py2app"]["plist"]
        self.assertEqual(
            plist["CFBundleIdentifier"], "com.minimalharness.desktop"
        )


if __name__ == "__main__":
    unittest.main()
