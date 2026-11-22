"""Tests for complete research session archiving and verification."""

import json
import tempfile
import unittest
from pathlib import Path

from gui.research.archive import ArchiveService
from gui.research.evidence import EvidenceStore
from gui.research.ids import new_id
from gui.research.notes import NoteStore
from gui.research.sources import SourceStore
from gui.research.threads import ThreadStore
from gui.research.tombstones import write_thread_tombstone
from gui.research.transfers import TransferStore
from gui.store import SessionStore

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_PNG += (2).to_bytes(4, "big") + (3).to_bytes(4, "big")
_REQUIRED_KINDS = (
    "session_meta",
    "primary_transcript",
    "thread_meta",
    "thread_transcript",
    "note",
    "source",
    "evidence_meta",
    "evidence_png",
    "transfer",
    "restored_history_meta",
    "tombstone",
    "session_file",
)


def _archive_session(fixture):
    """Archive a fixture session with all of its stores.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.

    Returns
    -------
    tuple
        Archive service and manifest.
    """
    service = ArchiveService(fixture["root"])
    manifest = service.archive_session(
        fixture["record"],
        fixture["notes"],
        fixture["sources"],
        fixture["evidence"],
    )
    return service, manifest


def _other_note(fixture):
    """Create a note owned by a different session.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.

    Returns
    -------
    dict
        Note owned by the other session.
    """
    other = fixture["store"].create("Beta")
    scope = _other_scope(other)
    return fixture["notes"].create(scope, "T", "B", {})


def _scope(record, thread):
    """Build a global record scope.

    Parameters
    ----------
    record : SessionRecord
        Owning session.
    thread : dict
        Owning research thread.

    Returns
    -------
    dict
        Scope mapping.
    """
    return {
        "session_id": record.session_id,
        "thread_id": thread["id"],
        "thread_title_snapshot": thread["title"],
        "thread_deleted": False,
    }


def _session(store):
    """Create a session with a primary transcript.

    Parameters
    ----------
    store : SessionStore
        Session store.

    Returns
    -------
    SessionRecord
        New session.
    """
    record = store.create("Alpha")
    record.transcript.write_text(json.dumps({"role": "user"}) + "\n")
    return record


def _thread(record):
    """Create a research thread with one transcript line.

    Parameters
    ----------
    record : SessionRecord
        Owning session.

    Returns
    -------
    dict
        Thread metadata.
    """
    store = ThreadStore(record.folder)
    thread = store.create("Topic")
    store.transcript_path(thread["id"]).write_text('{"role": "agent"}\n')
    return thread


def _note(root, record, thread):
    """Create a note and one earlier revision.

    Parameters
    ----------
    root : pathlib.Path
        Research root.
    record : SessionRecord
        Owning session.
    thread : dict
        Owning thread.

    Returns
    -------
    tuple
        Note store and note record.
    """
    store = NoteStore(root)
    note = store.create(_scope(record, thread), "Title", "Body", {})
    store.update(note["id"], body_md="Body two")
    return store, note


def _source(root, record, thread):
    """Create one captured source.

    Parameters
    ----------
    root : pathlib.Path
        Research root.
    record : SessionRecord
        Owning session.
    thread : dict
        Owning thread.

    Returns
    -------
    tuple
        Source store and source record.
    """
    store = SourceStore(root)
    source = store.add(_scope(record, thread), "https://a.test", "A", "text")
    return store, source


def _evidence(root, record, thread, source):
    """Capture one evidence screenshot.

    Parameters
    ----------
    root : pathlib.Path
        Research root.
    record : SessionRecord
        Owning session.
    thread : dict
        Owning thread.
    source : dict
        Linked source.

    Returns
    -------
    tuple
        Evidence store and evidence record.
    """
    store = EvidenceStore(root)
    scope = _scope(record, thread)
    record = store.capture(scope, "https://a.test", _PNG, source["id"])
    return store, record


def _restored(record):
    """Write one restored primary history fixture.

    Parameters
    ----------
    record : SessionRecord
        Owning session.

    Returns
    -------
    str
        Restored history identifier.
    """
    history_id = new_id("rh")
    folder = record.folder / "restored" / history_id
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"id": history_id}))
    (folder / "transcript.jsonl").write_text('{"role": "user"}\n')
    return history_id


def _fixture(folder):
    """Build a session with every archivable record type.

    Parameters
    ----------
    folder : str
        Temporary parent directory.

    Returns
    -------
    dict
        Fixture records and stores.
    """
    root = Path(folder) / "research"
    store = SessionStore(Path(folder) / "sessions")
    record = _session(store)
    thread = _thread(record)
    stores = _global_fixture(root, record, thread)
    _session_fixture(record, root, thread, stores)
    return _records(root, store, record, stores)


def _global_fixture(root, record, thread):
    """Build the global note, source, and evidence fixture.

    Parameters
    ----------
    root : pathlib.Path
        Research root.
    record : SessionRecord
        Owning session.
    thread : dict
        Owning thread.

    Returns
    -------
    dict
        Global stores and records.
    """
    note_store, note = _note(root, record, thread)
    source_store, source = _source(root, record, thread)
    evidence_store, evidence = _evidence(root, record, thread, source)
    stores = {"notes": note_store, "sources": source_store}
    stores.update({"evidence": evidence_store, "note": note})
    stores.update({"source": source, "evidence_record": evidence})
    return stores


def _session_fixture(record, root, thread, stores):
    """Build session-local and tombstone fixture files.

    Parameters
    ----------
    record : SessionRecord
        Owning session.
    root : pathlib.Path
        Research root.
    thread : dict
        Owning thread.
    stores : dict
        Global stores and records.

    Returns
    -------
    None
        Files are written.
    """
    TransferStore(record.folder).append("primary_to_research", "message", "x")
    write_thread_tombstone(
        root, thread, [stores["note"]["id"]], [stores["source"]["id"]]
    )
    _restored(record)
    (record.folder / "unknown.bin").write_bytes(b"keep")


def _records(root, store, record, stores):
    """Build the fixture result with the configured stores.

    Parameters
    ----------
    root : pathlib.Path
        Research root.
    store : SessionStore
        Session store.
    record : SessionRecord
        Archived session.
    stores : dict
        Global stores and records.

    Returns
    -------
    dict
        Fixture records and stores.
    """
    result = {"root": root, "store": store, "record": record}
    result.update({"notes": stores["notes"], "sources": stores["sources"]})
    result["evidence"] = stores["evidence"]
    return result


class ArchiveTests(unittest.TestCase):
    """Verify archive completeness, live deletion, and tamper detection."""

    def _archive(self, folder):
        """Archive the fixture session.

        Parameters
        ----------
        folder : str
            Temporary parent directory.

        Returns
        -------
        tuple
            Fixture, service, and manifest.
        """
        fixture = _fixture(folder)
        service, manifest = _archive_session(fixture)
        return fixture, service, manifest

    def test_archive_captures_every_record_type(self) -> None:
        """Record every required category in the manifest.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Counts and paths include each record type.
        """
        with tempfile.TemporaryDirectory() as folder:
            _, _, manifest = self._archive(folder)
        kinds = manifest["counts"]
        for kind in _REQUIRED_KINDS:
            self.assertGreaterEqual(kinds.get(kind, 0), 1)
        self.assertGreater(manifest["counts"]["note_revision"], 0)

    def test_archive_removes_live_data(self) -> None:
        """Delete the session folder and scoped global records.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Live data is gone.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture, _, _ = self._archive(folder)
        self.assertFalse(fixture["record"].folder.exists())
        self.assertEqual(_live_globals(fixture), 0)

    def test_archive_keeps_other_sessions(self) -> None:
        """Leave records owned by another session untouched.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The other session records survive.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            note = _other_note(fixture)
            _archive_session(fixture)
            saved = fixture["notes"].get(note["id"])
        self.assertEqual(saved["title"], "T")

    def test_manifest_digest_and_verify(self) -> None:
        """Write a separate digest and verify a clean archive.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The digest exists and verification succeeds.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture, service, manifest = self._archive(folder)
            digest = fixture["root"] / "archives" / manifest["archive_id"]
            digest = digest / "manifest.sha256"
            result = service.verify(manifest["archive_id"])
            self.assertTrue(digest.exists())
        self.assertTrue(result["ok"])

    def test_tampered_file_is_detected(self) -> None:
        """Report a changed archived file.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Verification fails with a hash error.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture, service, manifest = self._archive(folder)
            target = _first_png(fixture["root"], manifest["archive_id"])
            target.write_bytes(b"tampered")
            result = service.verify(manifest["archive_id"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])

    def test_tampered_manifest_is_detected(self) -> None:
        """Report a changed manifest.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Verification fails with a digest error.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture, service, manifest = self._archive(folder)
            path = _archive_folder(fixture) / "manifest.json"
            path.write_text(path.read_text() + " ")
            result = service.verify(manifest["archive_id"])
        self.assertIn("manifest digest mismatch", result["errors"])


def _live_globals(fixture):
    """Count the live global records for the archived session.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.

    Returns
    -------
    int
        Live global record count.
    """
    record = fixture["record"]
    session = record.session_id
    count = len(fixture["notes"].list(session, status=None))
    count += len(fixture["sources"].list(session, status=None))
    count += len(fixture["evidence"].list(session, status=None))
    return count


def _other_scope(record):
    """Build a scope without a research thread.

    Parameters
    ----------
    record : SessionRecord
        Owning session.

    Returns
    -------
    dict
        Scope mapping.
    """
    return {
        "session_id": record.session_id,
        "thread_id": new_id("th"),
        "thread_title_snapshot": "Deleted",
        "thread_deleted": True,
    }


def _archive_folder(fixture):
    """Return the newest archive folder.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.

    Returns
    -------
    pathlib.Path
        Archive folder.
    """
    folders = [
        p for p in (fixture["root"] / "archives").iterdir() if p.is_dir()
    ]
    return sorted(folders)[-1]


def _first_png(root, archive_id):
    """Return one archived PNG path.

    Parameters
    ----------
    root : pathlib.Path
        Research root.
    archive_id : str
        Archive identifier.

    Returns
    -------
    pathlib.Path
        Evidence PNG path.
    """
    folder = root / "archives" / archive_id
    return sorted(folder.rglob("*.png"))[0]


if __name__ == "__main__":
    unittest.main()
