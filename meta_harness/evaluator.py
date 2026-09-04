"""Deterministic local evaluator for generated web applications."""

import subprocess
from pathlib import Path
from typing import Any


class AppEvaluator:
    """Evaluate required web files and JavaScript syntax deterministically."""

    def evaluate(self, root: Path | str) -> dict[str, Any]:
        """Score a web app workspace.

        Parameters
        ----------
        root : pathlib.Path or str
            Application workspace.

        Returns
        -------
        dict[str, Any]
            Deterministic score, checks, and missing files.
        """
        directory = Path(root)
        files = self._files(directory)
        checks = self._checks(directory, files)
        score = sum(checks.values()) / len(checks)
        return {"score": score, "checks": checks, "files": files}

    def _files(self, root: Path) -> dict[str, bool]:
        """Check required application files.

        Parameters
        ----------
        root : pathlib.Path
            Application workspace.

        Returns
        -------
        dict[str, bool]
            Required-file presence checks.
        """
        return {
            name: (root / name).is_file() and (root / name).stat().st_size > 0
            for name in ("index.html", "styles.css", "app.js")
        }

    def _checks(self, root: Path, files: dict[str, bool]) -> dict[str, bool]:
        """Build file and syntax checks.

        Parameters
        ----------
        root : pathlib.Path
            Application workspace.
        files : dict[str, bool]
            Required-file checks.

        Returns
        -------
        dict[str, bool]
            Deterministic evaluation checks.
        """
        checks = dict(files)
        checks.update(self._syntax_checks(root, files))
        return checks

    def _syntax_checks(
        self, root: Path, files: dict[str, bool]
    ) -> dict[str, bool]:
        """Build syntax and structure checks.

        Parameters
        ----------
        root : pathlib.Path
            Application workspace.
        files : dict[str, bool]
            Required-file checks.

        Returns
        -------
        dict[str, bool]
            Syntax and HTML checks.
        """
        javascript = files["app.js"] and self._node_ok(root / "app.js")
        html = (
            files["index.html"]
            and "<html" in (root / "index.html").read_text().lower()
        )
        return {"javascript_syntax": javascript, "html_structure": html}

    def _node_ok(self, path: Path) -> bool:
        """Check JavaScript syntax with Node.

        Parameters
        ----------
        path : pathlib.Path
            JavaScript file.

        Returns
        -------
        bool
            Whether Node accepts the file.
        """
        return self._node_result(path)

    def _node_result(self, path: Path) -> bool:
        """Run Node syntax validation.

        Parameters
        ----------
        path : pathlib.Path
            JavaScript file.

        Returns
        -------
        bool
            Whether Node accepts the file.
        """
        try:
            return self._node_process(path).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _node_process(self, path: Path) -> subprocess.CompletedProcess[str]:
        """Run Node syntax checking.

        Parameters
        ----------
        path : pathlib.Path
            JavaScript file.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Node process result.
        """
        return subprocess.run(
            ["node", "--check", str(path)], capture_output=True, timeout=15
        )
