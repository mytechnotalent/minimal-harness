"""Build and install the macOS alias app bundle."""

import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "Minimal Harness"


def main() -> int:
    """Build and install the app bundle.

    Returns
    -------
    int
        Process exit code.
    """
    if sys.platform != "darwin":
        print("Building the macOS app bundle requires macOS.")
        return 1
    root = Path(__file__).resolve().parent.parent
    _build(root)
    target = _install(root)
    print(target)
    return 0


def _build(root: Path) -> None:
    """Run py2app in alias mode.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    None
        The bundle is built under ``dist``.
    """
    python = root / ".venv" / "bin" / "python"
    subprocess.run(
        [str(python), "setup_app.py", "py2app", "-A"],
        cwd=root,
        check=True,
    )


def _install(root: Path) -> Path:
    """Copy the built bundle into the user's Applications folder.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    pathlib.Path
        Installed bundle path.
    """
    source = root / "dist" / (APP_NAME + ".app")
    target = Path.home() / "Applications" / (APP_NAME + ".app")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target


if __name__ == "__main__":
    sys.exit(main())
