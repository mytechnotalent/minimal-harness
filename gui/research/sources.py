"""Persistent global source store with deduplication and occurrences."""

import copy
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from .atomic import read_json
from .atomic import write_json_atomic
from .hashing import hash_json
from .ids import new_id
from .ids import require_id
from .schemas import validate_source

SOURCE_PREFIX = "src"


class SourceStore:
    """Store captured citations outside thread folders."""

    def __init__(self, root):
        """Prepare the source store at a research root.

        Parameters
        ----------
        root : pathlib.Path or str
            Research data root.

        Returns
        -------
        None
            The source directory exists.
        """
        self.root = Path(root)
        self.sources = self.root / "sources"
        self.sources.mkdir(parents=True, exist_ok=True)

    def add(self, scope, url, title, excerpt, origin=None):
        """Capture a source or append a duplicate occurrence.

        Parameters
        ----------
        scope : dict
            Session, thread, and title scope.
        url : str
            Source URL.
        title : str
            Source title.
        excerpt : str
            Stored excerpt.
        origin : dict or None
            Optional tool, call, and sequence details.

        Returns
        -------
        dict
            Stored source record.
        """
        facts = _facts(scope, url, title, excerpt, origin or {})
        session_id = scope["session_id"]
        existing = self._find(session_id, facts)
        if existing is not None:
            return self._repeat(existing, facts)
        record = _new_source(facts)
        self.save(record)
        return record

    def save(self, source):
        """Validate and write one source record.

        Parameters
        ----------
        source : dict
            Source record.

        Returns
        -------
        None
            The source is written atomically.
        """
        validate_source(source)
        write_json_atomic(self._path(source["id"]), source)

    def get(self, source_id):
        """Load one source by identifier.

        Parameters
        ----------
        source_id : str
            Source identifier.

        Returns
        -------
        dict
            Source record.
        """
        require_id(source_id, SOURCE_PREFIX)
        return read_json(self._path(source_id))

    def list(self, session_id=None, thread_id=None, status="active"):
        """List sources filtered by scope and status.

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
            Matching source records.
        """
        sources = [read_json(path) for path in self._paths()]
        return [
            s for s in sources if _matches(s, session_id, thread_id, status)
        ]

    def delete(self, source_id):
        """Delete one source record.

        Parameters
        ----------
        source_id : str
            Source identifier.

        Returns
        -------
        None
            The source file is removed.
        """
        require_id(source_id, SOURCE_PREFIX)
        self._path(source_id).unlink(missing_ok=True)

    def _find(self, session_id, facts):
        """Find an equivalent source in the same session.

        Parameters
        ----------
        session_id : str
            Session scope.
        facts : dict
            Candidate source facts.

        Returns
        -------
        dict or None
            Existing source record.
        """
        for source in self.list(session_id, status=None):
            if _equivalent(source, facts):
                return source
        return None

    def _repeat(self, source, facts):
        """Append an occurrence to an existing source.

        Parameters
        ----------
        source : dict
            Existing source record.
        facts : dict
            New occurrence facts.

        Returns
        -------
        dict
            Updated source record.
        """
        updated = copy.deepcopy(source)
        occurrence = _occurrence(facts)
        _append_once(updated["occurrences"], occurrence)
        self.save(updated)
        return updated

    def _paths(self):
        """Return source file paths in sorted order.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Source JSON paths.
        """
        return sorted(self.sources.glob("src_*.json"))

    def _path(self, source_id):
        """Return one source file path.

        Parameters
        ----------
        source_id : str
            Source identifier.

        Returns
        -------
        pathlib.Path
            Source JSON path.
        """
        return self.sources / f"{source_id}.json"


def canonical_url(url):
    """Normalize a source URL for deduplication.

    Parameters
    ----------
    url : str
        Raw source URL.

    Returns
    -------
    str
        Normalized HTTP or HTTPS URL.
    """
    parts = urlsplit(url.strip())
    _require_web(parts)
    return _assemble_url(parts)


def _require_web(parts):
    """Require an HTTP or HTTPS URL with a host.

    Parameters
    ----------
    parts : urllib.parse.SplitResult
        Parsed URL.

    Returns
    -------
    None
        The URL is accepted.
    """
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("source URL must be http or https")


def _assemble_url(parts):
    """Rebuild a URL without its fragment.

    Parameters
    ----------
    parts : urllib.parse.SplitResult
        Parsed URL.

    Returns
    -------
    str
        Normalized URL.
    """
    path = parts.path or "/"
    scheme = parts.scheme.lower()
    return urlunsplit((scheme, _netloc(parts), path, parts.query, ""))


def _netloc(parts):
    """Return a normalized network location.

    Parameters
    ----------
    parts : urllib.parse.SplitResult
        Parsed URL.

    Returns
    -------
    str
        Lowercase host with an optional port.
    """
    host = parts.hostname.lower()
    return f"{host}:{parts.port}" if parts.port else host


def _facts(scope, url, title, excerpt, origin):
    """Build normalized source facts.

    Parameters
    ----------
    scope : dict
        Session, thread, and title scope.
    url : str
        Source URL.
    title : str
        Source title.
    excerpt : str
        Stored excerpt.
    origin : dict
        Tool, call, and sequence details.

    Returns
    -------
    dict
        Normalized source facts.
    """
    canonical = canonical_url(url)
    content = {"url": canonical, "title": title, "excerpt": excerpt}
    facts = _facts_scope(scope, canonical)
    facts.update(_facts_origin(origin))
    facts["title"] = title
    facts["excerpt"] = excerpt
    facts["content_hash"] = hash_json(content)
    return facts


def _facts_scope(scope, canonical):
    """Build the scope and URL fields of source facts.

    Parameters
    ----------
    scope : dict
        Session, thread, and title scope.
    canonical : str
        Normalized URL.

    Returns
    -------
    dict
        Scope fields.
    """
    return {
        "session_id": scope["session_id"],
        "thread_id": scope["thread_id"],
        "thread_title": scope["thread_title"],
        "url": canonical,
    }


def _facts_origin(origin):
    """Build the capturing fields of source facts.

    Parameters
    ----------
    origin : dict
        Tool, call, and sequence details.

    Returns
    -------
    dict
        Origin fields.
    """
    return {
        "tool": origin.get("tool", ""),
        "tool_call_id": origin.get("tool_call_id"),
        "message_seq": origin.get("message_seq"),
        "evidence_label": origin.get("evidence_label", "unknown"),
    }


def _new_source(facts):
    """Build a new source record.

    Parameters
    ----------
    facts : dict
        Normalized source facts.

    Returns
    -------
    dict
        New source record.
    """
    now = time.time()
    record = _source_ids(facts, now)
    record.update(_source_text(facts, now))
    record.update(_source_state())
    record["occurrences"] = [_occurrence(facts)]
    return record


def _source_ids(facts, now):
    """Build source identity, scope, and origin fields.

    Parameters
    ----------
    facts : dict
        Normalized source facts.
    now : float
        Capture timestamp.

    Returns
    -------
    dict
        Identity fields.
    """
    return {
        "id": new_id(SOURCE_PREFIX),
        "scope": _scope(facts),
        "origin": _origin(facts),
        "retrieved_at": now,
    }


def _source_text(facts, now):
    """Build source display fields.

    Parameters
    ----------
    facts : dict
        Normalized source facts.
    now : float
        Capture timestamp.

    Returns
    -------
    dict
        Display fields.
    """
    return {
        "url": facts["url"],
        "title": facts.get("title", ""),
        "excerpt": facts.get("excerpt", ""),
        "content_hash": facts["content_hash"],
        "evidence_label": facts.get("evidence_label", "unknown"),
    }


def _source_state():
    """Build initial source state.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        State fields.
    """
    return {"status": "active", "restored": None}


def _scope(facts):
    """Build a source scope mapping.

    Parameters
    ----------
    facts : dict
        Normalized source facts.

    Returns
    -------
    dict
        Scope mapping.
    """
    return {
        "session_id": facts["session_id"],
        "thread_id": facts["thread_id"],
        "thread_title_snapshot": facts["thread_title"],
        "thread_deleted": False,
    }


def _origin(facts):
    """Build a source origin mapping.

    Parameters
    ----------
    facts : dict
        Normalized source facts.

    Returns
    -------
    dict
        Origin mapping.
    """
    return {
        "message_seq": facts.get("message_seq"),
        "tool": facts.get("tool", ""),
        "tool_call_id": facts.get("tool_call_id"),
    }


def _occurrence(facts):
    """Build one source occurrence.

    Parameters
    ----------
    facts : dict
        Normalized source facts.

    Returns
    -------
    dict
        Occurrence mapping.
    """
    return {
        "thread_id": facts["thread_id"],
        "thread_title_snapshot": facts["thread_title"],
        "message_seq": facts.get("message_seq"),
        "tool": facts.get("tool", ""),
        "tool_call_id": facts.get("tool_call_id"),
    }


def _append_once(items, occurrence):
    """Append an occurrence unless it already exists.

    Parameters
    ----------
    items : list
        Occurrence list.
    occurrence : dict
        Candidate occurrence.

    Returns
    -------
    None
        The occurrence is appended when new.
    """
    if occurrence not in items:
        items.append(occurrence)


def _equivalent(source, facts):
    """Return whether a source matches candidate facts.

    Parameters
    ----------
    source : dict
        Existing source.
    facts : dict
        Candidate facts.

    Returns
    -------
    bool
        ``True`` for the same URL and content hash.
    """
    return (
        source.get("url") == facts["url"]
        and source.get("content_hash") == facts["content_hash"]
    )


def _matches(source, session_id, thread_id, status):
    """Return whether a source passes scope and status filters.

    Parameters
    ----------
    source : dict
        Source record.
    session_id : str or None
        Session filter.
    thread_id : str or None
        Thread filter.
    status : str or None
        Status filter.

    Returns
    -------
    bool
        ``True`` when the source matches.
    """
    scope = source.get("scope", {})
    if session_id is not None and scope.get("session_id") != session_id:
        return False
    if thread_id is not None and scope.get("thread_id") != thread_id:
        return False
    return status is None or source.get("status") == status
