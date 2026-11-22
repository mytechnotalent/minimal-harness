"""Tests for the global source store and occurrence deduplication."""

import tempfile
import unittest

from gui.research.sources import SourceStore
from gui.research.sources import canonical_url


def _scope(session="session", thread=None):
    """Build a source scope mapping.

    Parameters
    ----------
    session : str
        Session identifier.
    thread : str or None
        Thread identifier.

    Returns
    -------
    dict
        Scope mapping.
    """
    thread_id = thread or "th_" + "0" * 32
    return {
        "session_id": session,
        "thread_id": thread_id,
        "thread_title": "Thread",
    }


def _add(store, scope, url="https://example.com/a", title="Example"):
    """Add one source for a test.

    Parameters
    ----------
    store : SourceStore
        Source store.
    scope : dict
        Source scope.
    url : str
        Source URL.
    title : str
        Source title.

    Returns
    -------
    dict
        Stored source.
    """
    return store.add(scope, url, title, "excerpt")


class SourceStoreTests(unittest.TestCase):
    """Verify capture, normalization, deduplication, and filtering."""

    def test_add_and_get(self) -> None:
        """Persist and reload a source.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Stored fields match.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = SourceStore(folder)
            source = _add(store, _scope())
            loaded = store.get(source["id"])
        self.assertEqual(loaded["title"], "Example")
        self.assertEqual(loaded["scope"]["session_id"], "session")

    def test_url_is_canonicalized(self) -> None:
        """Lowercase the host and drop the fragment.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The stored URL is normalized.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = SourceStore(folder)
            source = _add(store, _scope(), "HTTPS://Example.com/a#frag")
        self.assertEqual(source["url"], "https://example.com/a")

    def test_duplicate_appends_occurrence(self) -> None:
        """Keep one source and add another occurrence.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The source is not duplicated.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = SourceStore(folder)
            first = _add(store, _scope())
            second = _add(store, _scope(thread="th_" + "1" * 32))
            sources = store.list(status=None)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(second["occurrences"]), 2)

    def test_different_excerpt_creates_source(self) -> None:
        """Create a new source when content differs.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both sources are stored.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = SourceStore(folder)
            first = _add(store, _scope())
            second = store.add(_scope(), "https://example.com/a", "T", "other")
            sources = store.list(status=None)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(sources), 2)

    def test_list_filters_by_session(self) -> None:
        """Return only sources in the requested session.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The other session is excluded.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = SourceStore(folder)
            _add(store, _scope("one"))
            _add(store, _scope("two"))
            sources = store.list("one")
        self.assertEqual([s["scope"]["session_id"] for s in sources], ["one"])

    def test_non_http_url_is_rejected(self) -> None:
        """Reject file and other schemes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ValueError is raised.
        """
        with self.assertRaises(ValueError):
            canonical_url("file:///etc/passwd")

    def test_delete_removes_source(self) -> None:
        """Delete one source file.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The source no longer loads.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = SourceStore(folder)
            source = _add(store, _scope())
            store.delete(source["id"])
            self.assertEqual(store.list(status=None), [])


if __name__ == "__main__":
    unittest.main()
