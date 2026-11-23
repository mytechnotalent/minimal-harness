"""Stable research identifiers and restore ID mapping."""

import copy
import re
import uuid

from .atomic import read_json
from .atomic import write_json_atomic
from .hashing import canonical_json
from .hashing import sha256_text

_ID_PATTERN = re.compile(r"^[a-z]{2,3}_[0-9a-f]{32}$")


def new_id(prefix):
    """Return a new prefixed identifier.

    Parameters
    ----------
    prefix : str
        Lowercase record prefix without the trailing underscore.

    Returns
    -------
    str
        New identifier.
    """
    if not prefix.isalpha() or not prefix.islower():
        raise ValueError("prefix must be lowercase letters")
    return f"{prefix}_{uuid.uuid4().hex}"


def is_valid_id(value, prefix=None):
    """Return whether a value is a valid research identifier.

    Parameters
    ----------
    value : object
        Candidate identifier.
    prefix : str or None
        Optional required prefix.

    Returns
    -------
    bool
        ``True`` for a valid identifier.
    """
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        return False
    return prefix is None or value.startswith(prefix + "_")


def require_id(value, prefix):
    """Return a valid identifier or raise.

    Parameters
    ----------
    value : object
        Candidate identifier.
    prefix : str
        Required prefix.

    Returns
    -------
    str
        The validated identifier.
    """
    if not is_valid_id(value, prefix):
        raise ValueError(f"invalid {prefix} identifier")
    return value


def message_hash(message):
    """Return the canonical hash of one transcript message.

    Parameters
    ----------
    message : dict
        One transcript message.

    Returns
    -------
    str
        Hexadecimal message hash.
    """
    return sha256_text(canonical_json(message))


def message_identity(sequence, message):
    """Return a stable identity for a transcript message.

    Parameters
    ----------
    sequence : int
        Zero-based transcript line index.
    message : dict
        One transcript message.

    Returns
    -------
    dict
        Sequence and hash identity.
    """
    return {"seq": sequence, "hash": message_hash(message)}


class IdMap:
    """Track original-to-restored identifiers for one operation."""

    def __init__(self, restore_id):
        """Configure a mapping for one restore.

        Parameters
        ----------
        restore_id : str
            Restore identifier.

        Returns
        -------
        None
            The mapping is empty.
        """
        self.restore_id = restore_id
        self.id_map = {}

    def add(self, kind, original, restored):
        """Record one identifier mapping.

        Parameters
        ----------
        kind : str
            Record kind.
        original : str
            Original identifier.
        restored : str
            Restored identifier.

        Returns
        -------
        None
            The mapping is stored.
        """
        bucket = self.id_map.setdefault(kind, {})
        bucket[original] = restored

    def new(self, kind, prefix, original):
        """Allocate and record a new identifier.

        Parameters
        ----------
        kind : str
            Record kind.
        prefix : str
            Identifier prefix.
        original : str
            Original identifier.

        Returns
        -------
        str
            New identifier.
        """
        restored = new_id(prefix)
        self.add(kind, original, restored)
        return restored

    def get(self, kind, original):
        """Return a mapped identifier or ``None``.

        Parameters
        ----------
        kind : str
            Record kind.
        original : str
            Original identifier.

        Returns
        -------
        str or None
            Restored identifier.
        """
        return self.id_map.get(kind, {}).get(original)

    def require(self, kind, original):
        """Return a mapped identifier or raise.

        Parameters
        ----------
        kind : str
            Record kind.
        original : str
            Original identifier.

        Returns
        -------
        str
            Restored identifier.
        """
        restored = self.get(kind, original)
        if restored is None:
            raise KeyError(f"no {kind} mapping for {original}")
        return restored

    def remap(self, kind, values):
        """Map a sequence of original identifiers.

        Parameters
        ----------
        kind : str
            Record kind.
        values : collections.abc.Iterable
            Original identifiers.

        Returns
        -------
        list
            Restored identifiers.
        """
        return [self.require(kind, value) for value in values]

    def to_dict(self):
        """Return a serializable mapping document.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Restore identifier and mapping.
        """
        return {
            "restore_id": self.restore_id,
            "id_map": copy.deepcopy(self.id_map),
        }

    def save(self, path):
        """Persist the mapping to a JSON file.

        Parameters
        ----------
        path : pathlib.Path or str
            Destination file.

        Returns
        -------
        None
            The mapping is written atomically.
        """
        write_json_atomic(path, self.to_dict())

    @classmethod
    def load(cls, path):
        """Load a mapping from a JSON file.

        Parameters
        ----------
        path : pathlib.Path or str
            Source file.

        Returns
        -------
        IdMap
            Loaded mapping.
        """
        data = read_json(path)
        mapping = cls(data["restore_id"])
        mapping.id_map = data.get("id_map", {})
        return mapping
