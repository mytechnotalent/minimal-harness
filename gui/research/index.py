"""Rebuildable full-text search index for research records."""

import sqlite3
import time
from pathlib import Path

_COLUMNS = (
    "record_type",
    "record_id",
    "session_id",
    "thread_id",
    "title",
    "body",
    "status",
    "updated",
)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    record_type TEXT NOT NULL,
    record_id TEXT PRIMARY KEY,
    session_id TEXT,
    thread_id TEXT,
    title TEXT,
    body TEXT,
    status TEXT,
    updated REAL
)
"""


class SearchIndex:
    """Store searchable research documents in a rebuildable database."""

    def __init__(self, path):
        """Open or create the index at a path.

        Parameters
        ----------
        path : pathlib.Path or str
            SQLite database path.

        Returns
        -------
        None
            The schema is ready.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path))
        self._ensure_schema()

    def close(self):
        """Close the database connection.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The connection is closed.
        """
        self._connection.close()

    def upsert(
        self,
        record_type,
        record_id,
        session_id=None,
        thread_id=None,
        title="",
        body="",
        status="active",
        updated=None,
    ):
        """Insert or replace one searchable document.

        Parameters
        ----------
        record_type : str
            Document type.
        record_id : str
            Document identifier.
        session_id : str or None
            Session scope.
        thread_id : str or None
            Thread scope.
        title : str
            Searchable title.
        body : str
            Searchable body.
        status : str
            Record status.
        updated : float or None
            Update timestamp.

        Returns
        -------
        None
            The document is stored.
        """
        stamp = time.time() if updated is None else updated
        values = [record_type, record_id, session_id, thread_id]
        values.extend([title, body, status, stamp])
        _replace(self._connection, tuple(values))

    def delete(self, record_id):
        """Delete one document by identifier.

        Parameters
        ----------
        record_id : str
            Document identifier.

        Returns
        -------
        None
            The document is removed.
        """
        self._connection.execute(
            "DELETE FROM documents WHERE record_id = ?", (record_id,)
        )
        self._connection.commit()

    def rebuild(self, documents):
        """Replace the index with a list of documents.

        Parameters
        ----------
        documents : collections.abc.Iterable
            Document mappings.

        Returns
        -------
        None
            The index is rebuilt.
        """
        with self._connection:
            self._connection.execute("DELETE FROM documents")
            for document in documents:
                _insert(self._connection, document)

    def search(self, query, session_id=None, include_archived=True, limit=50):
        """Search titles and bodies.

        Parameters
        ----------
        query : str
            Search text.
        session_id : str or None
            Optional session filter.
        include_archived : bool
            Whether archived records are included.
        limit : int
            Maximum result count.

        Returns
        -------
        list
            Matching document mappings.
        """
        pattern = f"%{query}%"
        clauses, params = _filters(session_id, include_archived, pattern)
        params.append(limit)
        return self._query(" AND ".join(clauses), params)

    def _ensure_schema(self):
        """Create the documents table when missing.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The schema exists.
        """
        self._connection.execute(_SCHEMA)
        self._connection.commit()

    def _query(self, where, params):
        """Run a filtered document query.

        Parameters
        ----------
        where : str
            SQL predicate.
        params : list
            Query parameters.

        Returns
        -------
        list
            Matching document mappings.
        """
        sql = "SELECT * FROM documents WHERE " + where
        sql += " ORDER BY updated DESC LIMIT ?"
        rows = self._connection.execute(sql, params).fetchall()
        return [_row(row) for row in rows]


def _replace(connection, row):
    """Insert or replace one row.

    Parameters
    ----------
    connection : sqlite3.Connection
        Open database connection.
    row : tuple
        Row values.

    Returns
    -------
    None
        The row is committed.
    """
    sql = "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    connection.execute(sql, row)
    connection.commit()


def _insert(connection, document):
    """Insert one document mapping without committing.

    Parameters
    ----------
    connection : sqlite3.Connection
        Open database connection.
    document : dict
        Document mapping.

    Returns
    -------
    None
        The row is queued.
    """
    values = tuple(document.get(name) for name in _COLUMNS[:-1])
    values += (document.get("updated", 0),)
    connection.execute(
        "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        values,
    )


def _filters(session_id, include_archived, pattern):
    """Build search predicates and parameters.

    Parameters
    ----------
    session_id : str or None
        Optional session filter.
    include_archived : bool
        Whether archived records are included.
    pattern : str
        LIKE pattern.

    Returns
    -------
    tuple
        Clause list and parameter list.
    """
    clauses = ["(title LIKE ? OR body LIKE ?)"]
    params = [pattern, pattern]
    if session_id is not None:
        clauses.append("session_id = ?")
        params.append(session_id)
    if not include_archived:
        clauses.append("status = 'active'")
    return clauses, params


def _row(row):
    """Build a document mapping from a database row.

    Parameters
    ----------
    row : tuple
        Database row.

    Returns
    -------
    dict
        Document mapping.
    """
    return dict(zip(_COLUMNS, row))
