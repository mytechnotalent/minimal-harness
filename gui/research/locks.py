"""Single-operation lock files for archival and restore work."""

import ctypes
import json
import os
import time
import uuid
from pathlib import Path

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5


class LockError(RuntimeError):
    """Report that another research operation holds the lock."""


class OperationLock:
    """Serialize archive, restore, purge, and migration operations."""

    def __init__(self, path, operation="research"):
        """Configure a lock at one path.

        Parameters
        ----------
        path : pathlib.Path or str
            Lock file path.
        operation : str
            Operation name recorded in the lock.

        Returns
        -------
        None
            The lock object is configured.
        """
        self.path = Path(path)
        self.operation = operation
        self.token = uuid.uuid4().hex

    def __enter__(self):
        """Acquire the lock for a context block.

        Parameters
        ----------
        None

        Returns
        -------
        OperationLock
            The acquired lock.
        """
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback):
        """Release the lock after a context block.

        Parameters
        ----------
        exc_type : type or None
            Exception type, if any.
        exc : BaseException or None
            Exception instance, if any.
        traceback : object or None
            Exception traceback, if any.

        Returns
        -------
        bool
            ``False`` so exceptions continue to propagate.
        """
        self.release()
        return False

    def acquire(self):
        """Create the lock file or raise when it is held.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The lock is held by this instance.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._remove_stale()
        try:
            self._create()
        except FileExistsError as exc:
            raise LockError(self._owner_message()) from exc

    def release(self):
        """Remove the lock file when this instance owns it.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The lock is released.
        """
        data = _read_lock(self.path)
        if data.get("token") == self.token:
            self.path.unlink(missing_ok=True)

    def _create(self):
        """Create and populate a new lock file.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The lock file exists.
        """
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        handle = os.open(self.path, flags, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(self._payload(), stream)
            stream.flush()
            os.fsync(stream.fileno())

    def _payload(self):
        """Build the lock owner record.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Owner metadata.
        """
        pid = os.getpid()
        return {
            "pid": pid,
            "process_start": _ps_start(pid),
            "operation": self.operation,
            "token": self.token,
            "started": time.time(),
        }

    def _remove_stale(self):
        """Remove a lock whose owner is gone.

        Parameters
        ----------
        None

        Returns
        -------
        None
            A stale lock is removed.
        """
        if not self.path.exists():
            return
        data = _read_lock(self.path)
        if not data or _is_stale(data):
            self.path.unlink(missing_ok=True)

    def _owner_message(self):
        """Describe the process that currently holds the lock.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Human-readable contention message.
        """
        data = _read_lock(self.path)
        owner = data.get("pid", "unknown")
        operation = data.get("operation", "research")
        return f"{operation} operation already running as pid {owner}"


def _read_lock(path):
    """Read a lock file without raising on corruption.

    Parameters
    ----------
    path : pathlib.Path
        Lock file.

    Returns
    -------
    dict
        Parsed lock data or an empty mapping.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _is_stale(data):
    """Return whether a recorded lock owner is no longer running.

    Parameters
    ----------
    data : dict
        Lock owner record.

    Returns
    -------
    bool
        ``True`` when the owner is gone or changed.
    """
    pid = data.get("pid")
    if not isinstance(pid, int) or not _alive(pid):
        return True
    return _start_mismatch(pid, data.get("process_start"))


def _alive(pid):
    """Return whether a process identifier is alive.

    Parameters
    ----------
    pid : int
        Process identifier.

    Returns
    -------
    bool
        ``True`` when the process exists.
    """
    if _is_windows():
        return _windows_alive(pid)
    return _posix_alive(pid)


def _is_windows():
    """Return whether the host uses Windows process semantics.

    Parameters
    ----------
    None

    Returns
    -------
    bool
        ``True`` on Windows.
    """
    return os.name == "nt"


def _posix_alive(pid):
    """Return whether a POSIX process identifier is alive.

    Parameters
    ----------
    pid : int
        Process identifier.

    Returns
    -------
    bool
        ``True`` when the process exists.
    """
    try:
        return _probe_process(pid)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _windows_alive(pid):
    """Return whether a Windows process identifier is alive.

    Parameters
    ----------
    pid : int
        Process identifier.

    Returns
    -------
    bool
        ``True`` when the process exists.
    """
    handle = _windows_handle(pid)
    if not handle:
        return _windows_error_alive()
    return _windows_probe(handle)


def _windows_handle(pid):
    """Open a query handle for one Windows process.

    Parameters
    ----------
    pid : int
        Process identifier.

    Returns
    -------
    int or None
        Process handle, or ``None`` when opening fails.
    """
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    return kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)


def _windows_probe(handle):
    """Query one open Windows process handle.

    Parameters
    ----------
    handle : int
        Open process handle.

    Returns
    -------
    bool
        ``True`` when the process is still active.
    """
    try:
        return _windows_active(handle)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _windows_active(handle):
    """Return whether an open Windows process is still active.

    Parameters
    ----------
    handle : int
        Open process handle.

    Returns
    -------
    bool
        ``True`` when the process is still active.
    """
    code = ctypes.c_ulong()
    kernel32 = ctypes.windll.kernel32
    if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
        return False
    return code.value == _STILL_ACTIVE


def _windows_error_alive():
    """Treat access-denied process handles as alive.

    Parameters
    ----------
    None

    Returns
    -------
    bool
        ``True`` when opening failed with access denied.
    """
    return ctypes.windll.kernel32.GetLastError() == _ERROR_ACCESS_DENIED


def _probe_process(pid):
    """Probe one process without handling platform errors.

    Parameters
    ----------
    pid : int
        Process identifier.

    Returns
    -------
    bool
        ``True`` when the probe succeeds.
    """
    os.kill(pid, 0)
    return True


def _start_mismatch(pid, recorded):
    """Return whether a process start time differs from the record.

    Parameters
    ----------
    pid : int
        Process identifier.
    recorded : str or None
        Recorded process start time.

    Returns
    -------
    bool
        ``True`` when the recorded start time is stale.
    """
    if recorded is None:
        return False
    return _ps_start(pid) != recorded


def _ps_start(pid):
    """Return a Linux process start time, when available.

    Parameters
    ----------
    pid : int
        Process identifier.

    Returns
    -------
    str or None
        Start time token, or ``None`` when unavailable.
    """
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    fields = text.rsplit(")", 1)[-1].split()
    return fields[19] if len(fields) > 19 else None
