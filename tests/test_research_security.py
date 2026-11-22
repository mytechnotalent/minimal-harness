"""Offline tests for the research security boundary."""

import tempfile
import unittest
from pathlib import Path

from meta_harness.tools import RESEARCH_TOOL_NAMES
from meta_harness.tools import ToolError
from meta_harness.tools import ToolRegistry


def _registry(root, **kwargs):
    """Build a read-only research registry for a workspace.

    Parameters
    ----------
    root : str
        Workspace directory.
    kwargs : dict
        Optional registry overrides.

    Returns
    -------
    ToolRegistry
        Restricted registry.
    """
    options = {
        "allowed_tools": RESEARCH_TOOL_NAMES,
        "read_only": True,
        "deny_private": True,
        "safe_urls": True,
    }
    options.update(kwargs)
    return ToolRegistry(root, **options)


def _seed(root):
    """Create allowed and denied workspace files.

    Parameters
    ----------
    root : pathlib.Path
        Workspace directory.

    Returns
    -------
    None
        Files are created.
    """
    (root / "ok.txt").write_text("public")
    (root / ".env").write_text("TOKEN=secret")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("TOKEN=secret")
    (root / "secrets").mkdir()
    (root / "secrets" / "a.txt").write_text("TOKEN=secret")
    (root / "id_rsa").write_text("TOKEN=secret")
    (root / "key.pem").write_text("TOKEN=secret")


def _assert_denied(case, registry, name):
    """Assert that a registry read is rejected.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    registry : ToolRegistry
        Restricted registry.
    name : str
        Workspace path.

    Returns
    -------
    None
        ToolError is raised.
    """
    with case.assertRaises(ToolError):
        registry.read(name)


class ResearchSecurityTests(unittest.TestCase):
    """Verify allowlists, read-only mode, and private-path denial."""

    def test_allowlist_hides_mutating_tools(self) -> None:
        """Advertise only read and research tools.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The allowlist is enforced.
        """
        with tempfile.TemporaryDirectory() as folder:
            registry = _registry(folder)
        names = registry._advertised_names()
        self.assertIn("read", names)
        self.assertNotIn("write", names)
        self.assertNotIn("bash", names)

    def test_read_only_write_is_rejected(self) -> None:
        """Reject a direct write even when bypassing the schema.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ToolError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            registry = _registry(folder)
            with self.assertRaises(ToolError):
                registry.write("new.txt", "x")

    def test_private_paths_are_denied(self) -> None:
        """Reject credentials, secrets, and app data paths.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Denied reads raise and allowed reads succeed.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _seed(root)
            registry = _registry(root)
            for name in (".env", ".git/config", "secrets/a.txt", "id_rsa"):
                _assert_denied(self, registry, name)
            self.assertEqual(registry.read("ok.txt")["content"], "public")

    def test_glob_and_repo_map_hide_private_paths(self) -> None:
        """Keep denied paths out of file discovery.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only the public file is listed.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _seed(root)
            registry = _registry(root)
            self.assertEqual(registry.glob("**/*")["files"], ["ok.txt"])
            self.assertNotIn("id_rsa", registry.repo_map()["files"])

    def test_grep_skips_private_files(self) -> None:
        """Do not return matches from denied files.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The secret token is not exposed.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _seed(root)
            registry = _registry(root)
            self.assertEqual(registry.grep("TOKEN")["matches"], [])

    def test_symlink_escape_is_rejected(self) -> None:
        """Reject a symlink that resolves outside the workspace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ToolError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "workspace"
            root.mkdir()
            outside = Path(folder) / "outside.txt"
            outside.write_text("secret")
            (root / "link").symlink_to(outside)
            registry = _registry(root)
            _assert_denied(self, registry, "link")


if __name__ == "__main__":
    unittest.main()
