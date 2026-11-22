"""Persistent research evidence screenshots with generated paths."""

import copy
import re
import time
from pathlib import Path

from .atomic import read_json
from .atomic import write_bytes_atomic
from .atomic import write_json_atomic
from .hashing import sha256_bytes
from .ids import new_id
from .ids import require_id
from .schemas import validate_evidence

EVIDENCE_PREFIX = "ev"
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_PNG_HEADER = b"\x89PNG\r\n\x1a\n"


class EvidenceStore:
    """Store screenshots and metadata outside the project workspace."""

    def __init__(self, root):
        """Prepare the evidence store at a research root.

        Parameters
        ----------
        root : pathlib.Path or str
            Research data root.

        Returns
        -------
        None
            The evidence directory exists.
        """
        self.root = Path(root)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir(parents=True, exist_ok=True)

    def capture(
        self,
        scope,
        url,
        data,
        source_id=None,
        caption="",
        tool_call_id=None,
    ):
        """Write one screenshot and its metadata pair.

        Parameters
        ----------
        scope : dict
            Session, thread, and title scope.
        url : str
            Captured URL.
        data : bytes
            PNG content.
        source_id : str or None
            Related source identifier.
        caption : str
            Optional caption.
        tool_call_id : str or None
            Tool call identifier.

        Returns
        -------
        dict
            Evidence record.
        """
        facts = _capture_facts(scope, url, data, source_id, caption)
        folder, evidence_id, png = self._prepare(scope)
        write_bytes_atomic(png, data)
        record = _evidence_record(evidence_id, facts, tool_call_id)
        validate_evidence(record)
        write_json_atomic(folder / f"{evidence_id}.json", record)
        return record

    def get(self, evidence_id):
        """Load one evidence record by identifier.

        Parameters
        ----------
        evidence_id : str
            Evidence identifier.

        Returns
        -------
        dict
            Evidence record.
        """
        require_id(evidence_id, EVIDENCE_PREFIX)
        return read_json(self._meta_path_for(evidence_id))

    def list(self, session_id=None, thread_id=None, status="active"):
        """List evidence filtered by scope and status.

        Parameters
        ----------
        session_id : str or None
            Optional session scope.
        thread_id : str or None
            Optional thread scope.
        status : str or None
            Optional status filter, or ``None`` for all.

        Returns
        -------
        list
            Matching evidence records.
        """
        records = [read_json(path) for path in self._metas()]
        return [
            r for r in records if _matches(r, session_id, thread_id, status)
        ]

    def mark_orphaned(self, evidence_id, reason="thread_deleted"):
        """Mark evidence as orphaned without deleting it.

        Parameters
        ----------
        evidence_id : str
            Evidence identifier.
        reason : str
            Orphan reason.

        Returns
        -------
        dict
            Updated evidence record.
        """
        record = self.get(evidence_id)
        updated = copy.deepcopy(record)
        updated["orphan"] = _orphan(updated, reason)
        write_json_atomic(self._meta_path(updated), updated)
        return updated

    def delete(self, evidence_id):
        """Delete one screenshot and its metadata.

        Parameters
        ----------
        evidence_id : str
            Evidence identifier.

        Returns
        -------
        None
            Both files are removed.
        """
        record = self.get(evidence_id)
        self._meta_path(record).unlink(missing_ok=True)
        self._png_path(record).unlink(missing_ok=True)

    def _prepare(self, scope):
        """Validate scope identifiers and prepare an evidence folder.

        Parameters
        ----------
        scope : dict
            Session, thread, and title scope.

        Returns
        -------
        tuple
            Folder, evidence identifier, and PNG path.
        """
        _require_segment(scope["session_id"])
        _require_segment(scope["thread_id"])
        evidence_id = new_id(EVIDENCE_PREFIX)
        folder = self.evidence / scope["session_id"] / scope["thread_id"]
        folder.mkdir(parents=True, exist_ok=True)
        return folder, evidence_id, folder / f"{evidence_id}.png"

    def _metas(self):
        """Return evidence metadata paths in sorted order.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Evidence JSON paths.
        """
        return sorted(self.evidence.rglob("ev_*.json"))

    def _meta_path_for(self, evidence_id):
        """Find the metadata path for an evidence identifier.

        Parameters
        ----------
        evidence_id : str
            Evidence identifier.

        Returns
        -------
        pathlib.Path
            Metadata path.
        """
        for path in self._metas():
            if path.stem == evidence_id:
                return path
        raise FileNotFoundError(evidence_id)

    def _meta_path(self, record):
        """Return the metadata path for a record.

        Parameters
        ----------
        record : dict
            Evidence record.

        Returns
        -------
        pathlib.Path
            Metadata path.
        """
        return self._folder(record) / f"{record['id']}.json"

    def _png_path(self, record):
        """Return the screenshot path for a record.

        Parameters
        ----------
        record : dict
            Evidence record.

        Returns
        -------
        pathlib.Path
            PNG path.
        """
        return self._folder(record) / f"{record['id']}.png"

    def _folder(self, record):
        """Return the scope folder for a record.

        Parameters
        ----------
        record : dict
            Evidence record.

        Returns
        -------
        pathlib.Path
            Session and thread folder.
        """
        scope = record["scope"]
        return self.evidence / scope["session_id"] / scope["thread_id"]


def _capture_facts(scope, url, data, source_id, caption):
    """Build evidence facts from capture inputs.

    Parameters
    ----------
    scope : dict
        Session, thread, and title scope.
    url : str
        Captured URL.
    data : bytes
        PNG content.
    source_id : str or None
        Related source identifier.
    caption : str
        Optional caption.

    Returns
    -------
    dict
        Capture facts.
    """
    facts = {"scope": dict(scope), "url": url, "data": data}
    facts.update(_capture_extra(source_id, caption))
    return facts


def _capture_extra(source_id, caption):
    """Build optional evidence capture fields.

    Parameters
    ----------
    source_id : str or None
        Related source identifier.
    caption : str
        Optional caption.

    Returns
    -------
    dict
        Optional fields.
    """
    return {"source_id": source_id, "caption": caption}


def _evidence_record(evidence_id, facts, tool_call_id):
    """Build one evidence record.

    Parameters
    ----------
    evidence_id : str
        Evidence identifier.
    facts : dict
        Capture facts.
    tool_call_id : str or None
        Tool call identifier.

    Returns
    -------
    dict
        Evidence record.
    """
    now = time.time()
    width, height = _png_size(facts["data"])
    record = {"id": evidence_id, "scope": dict(facts["scope"])}
    record.update(_evidence_body(facts, now, width, height))
    record.update(_evidence_links(facts, tool_call_id))
    return record


def _evidence_body(facts, now, width, height):
    """Build evidence file, timing, and source fields.

    Parameters
    ----------
    facts : dict
        Capture facts.
    now : float
        Capture timestamp.
    width : int
        Image width.
    height : int
        Image height.

    Returns
    -------
    dict
        File and source fields.
    """
    record = _evidence_file(facts)
    record.update(_evidence_size(facts["data"], now, width, height))
    return record


def _evidence_file(facts):
    """Build the source link and URL fields of evidence.

    Parameters
    ----------
    facts : dict
        Capture facts.

    Returns
    -------
    dict
        Source link fields.
    """
    return {"source_id": facts["source_id"], "url": facts["url"]}


def _evidence_size(data, now, width, height):
    """Build evidence timing, hash, and size fields.

    Parameters
    ----------
    data : bytes
        PNG content.
    now : float
        Capture timestamp.
    width : int
        Image width.
    height : int
        Image height.

    Returns
    -------
    dict
        Timing and size fields.
    """
    return {
        "captured_at": now,
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "width": width,
        "height": height,
    }


def _evidence_links(facts, tool_call_id):
    """Build evidence caption, tool, and state fields.

    Parameters
    ----------
    facts : dict
        Capture facts.
    tool_call_id : str or None
        Tool call identifier.

    Returns
    -------
    dict
        Caption and state fields.
    """
    return {
        "tool_call_id": tool_call_id,
        "caption": facts["caption"],
        "status": "active",
        "orphan": None,
        "restored": None,
    }


def _orphan(record, reason):
    """Build orphan metadata for one evidence record.

    Parameters
    ----------
    record : dict
        Evidence record.
    reason : str
        Orphan reason.

    Returns
    -------
    dict
        Orphan metadata.
    """
    scope = record.get("scope", {})
    return {
        "orphaned_at": time.time(),
        "reason": reason,
        "original_thread_id": scope.get("thread_id"),
        "original_thread_title_snapshot": scope.get("thread_title_snapshot"),
    }


def _png_size(data):
    """Return PNG width and height, or zero when unavailable.

    Parameters
    ----------
    data : bytes
        Candidate PNG content.

    Returns
    -------
    tuple
        Width and height.
    """
    if data[:8] != _PNG_HEADER or len(data) < 24:
        return 0, 0
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height


def _require_segment(value):
    """Validate one path segment used in evidence storage.

    Parameters
    ----------
    value : object
        Candidate segment.

    Returns
    -------
    None
        The segment is accepted.
    """
    if not isinstance(value, str) or _SEGMENT.fullmatch(value) is None:
        raise ValueError("invalid evidence path segment")
    if value in (".", ".."):
        raise ValueError("invalid evidence path segment")


def _matches(record, session_id, thread_id, status):
    """Return whether evidence passes scope and status filters.

    Parameters
    ----------
    record : dict
        Evidence record.
    session_id : str or None
        Session filter.
    thread_id : str or None
        Thread filter.
    status : str or None
        Status filter.

    Returns
    -------
    bool
        ``True`` when the record matches.
    """
    scope = record.get("scope", {})
    if session_id is not None and scope.get("session_id") != session_id:
        return False
    if thread_id is not None and scope.get("thread_id") != thread_id:
        return False
    return status is None or record.get("status") == status
