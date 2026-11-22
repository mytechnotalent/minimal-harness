"""Tests for the rebuildable research search index."""

import tempfile
import unittest
from pathlib import Path

from gui.research.index import SearchIndex


def _doc(record_id, title, body, session="one", status="active"):
    """Build one search document.

    Parameters
    ----------
    record_id : str
        Document identifier.
    title : str
        Searchable title.
    body : str
        Searchable body.
    session : str
        Session scope.
    status : str
        Record status.

    Returns
    -------
    dict
        Search document.
    """
    doc = {"record_type": "note", "record_id": record_id}
    doc.update({"session_id": session, "thread_id": None})
    doc.update({"title": title, "body": body, "status": status})
    doc["updated"] = 0
    return doc


def _search(docs, query, **kwargs):
    """Rebuild an index and run one search.

    Parameters
    ----------
    docs : list
        Documents to index.
    query : str
        Search text.
    kwargs : dict
        Search options.

    Returns
    -------
    list
        Matching documents.
    """
    with tempfile.TemporaryDirectory() as folder:
        index = SearchIndex(Path(folder) / "index.db")
        try:
            index.rebuild(docs)
            return index.search(query, **kwargs)
        finally:
            index.close()


def _delete(docs, record_id, query):
    """Delete one indexed document and search again.

    Parameters
    ----------
    docs : list
        Documents to index.
    record_id : str
        Document to delete.
    query : str
        Search text.

    Returns
    -------
    list
        Matching documents.
    """
    with tempfile.TemporaryDirectory() as folder:
        index = SearchIndex(Path(folder) / "index.db")
        try:
            index.rebuild(docs)
            index.delete(record_id)
            return index.search(query)
        finally:
            index.close()


def _replace(first, second, query):
    """Rebuild an index twice and search the final state.

    Parameters
    ----------
    first : list
        Initial documents.
    second : list
        Replacement documents.
    query : str
        Search text.

    Returns
    -------
    list
        Matching documents.
    """
    with tempfile.TemporaryDirectory() as folder:
        index = SearchIndex(Path(folder) / "index.db")
        try:
            index.rebuild(first)
            index.rebuild(second)
            return index.search(query)
        finally:
            index.close()


class SearchIndexTests(unittest.TestCase):
    """Verify rebuild, search, filtering, and deletion."""

    def test_rebuild_and_search(self) -> None:
        """Find documents by title or body text.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The matching document is returned.
        """
        rows = _search([_doc("a", "Alpha", "body")], "alpha")
        self.assertEqual([row["record_id"] for row in rows], ["a"])

    def test_search_filters_by_session(self) -> None:
        """Exclude documents from other sessions.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only the requested session is returned.
        """
        docs = [_doc("a", "Alpha", "x", "one")]
        docs.append(_doc("b", "Alpha", "x", "two"))
        rows = _search(docs, "alpha", session_id="one")
        self.assertEqual([row["record_id"] for row in rows], ["a"])

    def test_archived_can_be_excluded(self) -> None:
        """Filter archived documents when requested.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only active documents remain.
        """
        docs = [_doc("a", "Alpha", "x")]
        docs.append(_doc("b", "Alpha", "x", status="archived"))
        rows = _search(docs, "alpha", include_archived=False)
        self.assertEqual([row["record_id"] for row in rows], ["a"])

    def test_delete_removes_document(self) -> None:
        """Delete one indexed document.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The document no longer matches.
        """
        rows = _delete([_doc("a", "Alpha", "x")], "a", "alpha")
        self.assertEqual(rows, [])

    def test_rebuild_replaces_old_documents(self) -> None:
        """Discard previous documents during rebuild.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The old document is gone.
        """
        docs = [_doc("a", "Alpha", "x")]
        rows = _replace(docs, [_doc("b", "Beta", "x")], "alpha")
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
