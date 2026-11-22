"""Tests for research root resolution and workspace guarding."""

import tempfile
import unittest
from pathlib import Path

from gui.research.paths import ResearchPathError
from gui.research.paths import research_root


class ResearchPathTests(unittest.TestCase):
    """Verify root defaults, overrides, and workspace isolation."""

    def test_root_is_created_under_app_data(self) -> None:
        """Create a default research root under app data.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The root exists at the expected path.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = research_root(app_data=folder, env={})
            self.assertEqual(root, Path(folder).resolve() / "research")
            self.assertTrue(root.is_dir())

    def test_environment_override_is_used(self) -> None:
        """Use HARNESS_RESEARCH_DIR when present.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The override directory is created.
        """
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "custom"
            root = research_root(env={"HARNESS_RESEARCH_DIR": str(target)})
            self.assertEqual(root, target.resolve())
            self.assertTrue(root.is_dir())

    def test_overlap_with_workspace_is_rejected(self) -> None:
        """Refuse a research root inside the active workspace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ResearchPathError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ResearchPathError):
                research_root(app_data=folder, workspace=folder, env={})

    def test_sibling_workspace_is_allowed(self) -> None:
        """Allow a research root beside the workspace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The root is created outside the workspace.
        """
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "project"
            root = research_root(app_data=folder, workspace=workspace, env={})
            self.assertNotIn(workspace.resolve(), root.parents)


if __name__ == "__main__":
    unittest.main()
