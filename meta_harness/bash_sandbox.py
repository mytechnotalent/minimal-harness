"""OS-level confinement for answer-mode shell commands."""

import os
import shutil
import sys
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    """Raised when no supported OS sandbox can be found."""


_LINUX_FLAGS = (
    "--die-with-parent",
    "--new-session",
    "--unshare-ipc",
    "--unshare-pid",
    "--unshare-uts",
    "--cap-drop",
    "ALL",
)

_LINUX_SYSTEM = (
    "--ro-bind-try",
    "/usr",
    "/usr",
    "--ro-bind-try",
    "/bin",
    "/bin",
    "--ro-bind-try",
    "/sbin",
    "/sbin",
    "--ro-bind-try",
    "/lib",
    "/lib",
    "--ro-bind-try",
    "/lib64",
    "/lib64",
    "--ro-bind-try",
    "/lib32",
    "/lib32",
    "--ro-bind-try",
    "/etc",
    "/etc",
    "--ro-bind-try",
    "/opt",
    "/opt",
    "--ro-bind-try",
    "/nix",
    "/nix",
    "--ro-bind-try",
    "/snap",
    "/snap",
    "--ro-bind-try",
    "/run",
    "/run",
)

_LINUX_BINDS = (
    "--tmpfs",
    "/tmp",
    "--dev",
    "/dev",
    "--proc",
    "/proc",
    "--bind",
    "{root}",
    "{root}",
    "--chdir",
    "{root}",
)

_MACOS_PROFILE = """(version 1)
(allow default)
{network}(deny file-write*)
(allow file-write* (literal "/dev/null") (literal "/dev/stdout")
    (literal "/dev/stderr") (subpath "{root}") (subpath "/tmp")
    (subpath "/private/tmp") (subpath "/private/var/folders"))
"""


def sandbox_argv(root: Path, command: str) -> list[str] | None:
    """Return a confined command line, or ``None`` for host execution.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    command : str
        Shell command.

    Returns
    -------
    list of str or None
        Sandbox argument vector, or ``None`` when host execution is allowed.
    """
    mode = _sandbox_mode()
    if mode == "host":
        return None
    if sys.platform == "darwin":
        return _macos_argv(root, command)
    if sys.platform.startswith("linux"):
        return _linux_argv(root, command)
    raise SandboxUnavailable(_missing_message())


def _sandbox_mode() -> str:
    """Return the configured sandbox mode.

    Parameters
    ----------
    None

    Returns
    -------
    str
        ``host`` or ``auto``.
    """
    value = os.getenv("HARNESS_BASH_SANDBOX", "auto").strip().lower()
    if value in ("host", "0", "false", "no", "off"):
        return "host"
    if value in ("", "auto", "1", "true", "yes", "on", "os"):
        return "auto"
    raise SandboxUnavailable(f"unknown HARNESS_BASH_SANDBOX={value!r}")


def _network_allowed() -> bool:
    """Return whether bash may use the network.

    Parameters
    ----------
    None

    Returns
    -------
    bool
        ``True`` when HARNESS_BASH_NETWORK enables it.
    """
    value = os.getenv("HARNESS_BASH_NETWORK", "").strip().lower()
    return value in ("1", "true", "yes", "on")


def _linux_argv(root: Path, command: str) -> list[str]:
    """Build a bubblewrap argument vector.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    command : str
        Shell command.

    Returns
    -------
    list of str
        Sandboxed argument vector.
    """
    bwrap = _require_tool("bwrap")
    _check_root(root)
    args = [bwrap, *_LINUX_FLAGS, *_linux_binds(root)]
    if not _network_allowed():
        args.insert(1, "--unshare-net")
    return [*args, "/bin/sh", "-c", command]


def _linux_binds(root: Path) -> list[str]:
    """Expand the Linux bind template for one workspace.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    list of str
        Bubblewrap mount flags.
    """
    text = str(root)
    workspace = [part.format(root=text) for part in _LINUX_BINDS]
    return [*_LINUX_SYSTEM, *workspace]


def _macos_argv(root: Path, command: str) -> list[str]:
    """Build a sandbox-exec argument vector.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    command : str
        Shell command.

    Returns
    -------
    list of str
        Sandboxed argument vector.
    """
    _check_root(root)
    sandbox = _require_tool("sandbox-exec")
    profile = _macos_profile(root)
    return [sandbox, "-p", profile, "/bin/sh", "-c", command]


def _macos_profile(root: Path) -> str:
    """Build a sandbox-exec profile for one workspace.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    str
        Sandbox profile text.
    """
    network = "" if _network_allowed() else "(deny network*)\n"
    return _MACOS_PROFILE.format(network=network, root=_escape(root))


def _escape(root: Path) -> str:
    """Escape one path for a sandbox profile string.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    str
        Escaped path text.
    """
    return str(root).replace("\\", "\\\\").replace('"', '\\"')


def _check_root(root: Path) -> None:
    """Reject a workspace that is the filesystem root.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    None
        The root is accepted or ``SandboxUnavailable`` is raised.
    """
    if root == Path(root.anchor):
        raise SandboxUnavailable("sandbox refuses to bind the root")


def _require_tool(name: str) -> str:
    """Return an installed sandbox executable.

    Parameters
    ----------
    name : str
        Executable name.

    Returns
    -------
    str
        Resolved executable path.
    """
    path = shutil.which(name)
    if path is None:
        raise SandboxUnavailable(_missing_message())
    return path


def _missing_message() -> str:
    """Return the user-facing missing-sandbox message.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Error message naming the install and opt-out paths.
    """
    return (
        "No OS sandbox is available for bash. Install bubblewrap "
        "(Linux) or use HARNESS_BASH_SANDBOX=host to allow unrestricted "
        "host execution."
    )
