"""Canonical hashing helpers for research records and files."""

import hashlib
import json
from pathlib import Path

_BLOCK = 65536


def canonical_json(value):
    """Serialize a value into a stable canonical JSON string.

    Parameters
    ----------
    value : object
        JSON-compatible value.

    Returns
    -------
    str
        Canonical JSON text.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def sha256_bytes(data):
    """Return the SHA-256 hex digest of bytes.

    Parameters
    ----------
    data : bytes
        Data to hash.

    Returns
    -------
    str
        Hexadecimal digest.
    """
    return hashlib.sha256(data).hexdigest()


def sha256_text(text):
    """Return the SHA-256 hex digest of UTF-8 text.

    Parameters
    ----------
    text : str
        Text to encode and hash.

    Returns
    -------
    str
        Hexadecimal digest.
    """
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path):
    """Return the SHA-256 hex digest of a file.

    Parameters
    ----------
    path : pathlib.Path or str
        File to hash.

    Returns
    -------
    str
        Hexadecimal digest.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_json(value):
    """Return the SHA-256 hex digest of canonical JSON.

    Parameters
    ----------
    value : object
        JSON-compatible value.

    Returns
    -------
    str
        Hexadecimal digest.
    """
    return sha256_text(canonical_json(value))
