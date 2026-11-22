"""Atomic file writes, appends, and renames for research storage."""

import json
import os
import tempfile
from pathlib import Path


def write_bytes_atomic(path, data):
    """Write bytes to a path using a temporary file and rename.

    Parameters
    ----------
    path : pathlib.Path or str
        Destination file.
    data : bytes
        Content to write.

    Returns
    -------
    None
        The destination is replaced atomically.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp_path(target)
    try:
        _write_temp(temp, data)
        os.replace(temp, target)
    finally:
        _discard(temp)


def write_json_atomic(path, value):
    """Write a JSON document atomically.

    Parameters
    ----------
    path : pathlib.Path or str
        Destination file.
    value : object
        JSON-compatible value.

    Returns
    -------
    None
        The destination is replaced atomically.
    """
    text = json.dumps(value, indent=2, sort_keys=True, default=str)
    write_bytes_atomic(path, text.encode("utf-8") + b"\n")


def read_json(path):
    """Read a JSON document.

    Parameters
    ----------
    path : pathlib.Path or str
        Source file.

    Returns
    -------
    object
        Parsed JSON value.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def append_text(path, text):
    """Append text to a file and flush it to disk.

    Parameters
    ----------
    path : pathlib.Path or str
        Destination file.
    text : str
        Content to append.

    Returns
    -------
    None
        The text is appended.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def rename_atomic(source, target):
    """Rename a file or directory and sync the parent directory.

    Parameters
    ----------
    source : pathlib.Path or str
        Existing path.
    target : pathlib.Path or str
        Destination path.

    Returns
    -------
    None
        The rename is complete.
    """
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    _sync_dir(destination.parent)


def _temp_path(target):
    """Create an empty temporary file beside a destination.

    Parameters
    ----------
    target : pathlib.Path
        Destination file.

    Returns
    -------
    pathlib.Path
        Temporary path.
    """
    handle, name = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
    os.close(handle)
    return Path(name)


def _write_temp(path, data):
    """Write bytes into a temporary file and flush them.

    Parameters
    ----------
    path : pathlib.Path
        Temporary file.
    data : bytes
        Content to write.

    Returns
    -------
    None
        The content is flushed.
    """
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _discard(path):
    """Remove a temporary file when it still exists.

    Parameters
    ----------
    path : pathlib.Path
        Temporary file.

    Returns
    -------
    None
        Missing files are ignored.
    """
    try:
        Path(path).unlink()
    except FileNotFoundError:
        return


def _sync_dir(path):
    """Flush a directory entry to disk.

    Parameters
    ----------
    path : pathlib.Path
        Directory to sync.

    Returns
    -------
    None
        The directory metadata is flushed.
    """
    handle = os.open(path, os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)
