"""Tests for complete research session archiving and verification."""

import json
import tempfile
import unittest
from pathlib import Path

from gui.research.archive import ArchiveError
from gui.research.archive import ArchiveService
from gui.research.evidence import EvidenceStore
from gui.research.ids import new_id
from gui.research.notes import NoteStore
from gui.research.restored import RestoredHistoryStore
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
    meta = _restored_meta(record, history_id)
    (folder / "meta.json").write_text(json.dumps(meta))
    (folder / "transcript.jsonl").write_text('{"role": "user"}\n')
    return history_id


def _restored_meta(record, history_id):
    """Build a complete restored history metadata fixture.

    Parameters
    ----------
    record : SessionRecord
        Owning session.
    history_id : str
        Restored history identifier.

    Returns
    -------
    dict
        Restored history metadata.
    """
    meta = {"id": history_id, "target_session_id": record.session_id}
    meta.update(_restored_identity(record))
    meta.update(_restored_state())
    return meta


def _restored_identity(record):
    """Build history provenance fields for a fixture.

    Parameters
    ----------
    record : SessionRecord
        Owning session.

    Returns
    -------
    dict
        Provenance fields.
    """
    return {
        "archive_id": new_id("ar"),
        "restore_id": new_id("rs"),
        "original_session_id": record.session_id,
        "original_title": "Earlier",
    }


def _restored_state():
    """Build state, size, and access fields for a history fixture.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        State fields.
    """
    return {
        "archived_at": 1.0,
        "restored_at": 2.0,
        "message_count": 1,
        "sha256": "0" * 64,
        "read_only": True,
        "searchable": True,
    }


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
    _link_note(note_store, note, source, evidence)
    stores = {"notes": note_store, "sources": source_store}
    stores.update({"evidence": evidence_store, "note": note})
    stores.update({"source": source, "evidence_record": evidence})
    return stores


def _link_note(store, note, source, evidence):
    """Attach source and evidence references to a fixture note.

    Parameters
    ----------
    store : NoteStore
        Note store.
    note : dict
        Note record.
    source : dict
        Source record.
    evidence : dict
        Evidence record.

    Returns
    -------
    None
        The note is saved with references.
    """
    record = store.get(note["id"])
    record["source_ids"] = [source["id"]]
    record["evidence_ids"] = [evidence["id"]]
    store.save(record)


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
    TransferStore(record.folder).append(
        "primary_to_research", "message", "x", target_thread_id=thread["id"]
    )
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


class RestoreTests(unittest.TestCase):
    """Verify restores allocate new IDs, remap references, and stay safe."""

    def test_restore_new_session_gets_new_ids_and_remaps(self) -> None:
        """Restore into a new session with remapped references.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Identifiers and references are restored consistently.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            original = _original_ids(fixture)
            _assert_new_restore(self, fixture, original)

    def test_restore_makes_primary_transcript_active(self) -> None:
        """Copy the archived primary transcript into the new session.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The active transcript matches the archived one.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            expected = fixture["record"].transcript.read_text()
            _, manifest = _archive_session(fixture)
            session = _restored_session(fixture, manifest["archive_id"])
            self.assertEqual(session.transcript.read_text(), expected)

    def test_restore_existing_session_keeps_primary_history_read_only(
        self,
    ) -> None:
        """Store an archived primary transcript as restored history.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The active transcript is unchanged and history is present.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            _, manifest = _archive_session(fixture)
            session, before = _existing_session(fixture)
            _restore_into(fixture, manifest["archive_id"], session.session_id)
            histories = RestoredHistoryStore(session.folder).list()
            self.assertEqual(session.transcript.read_text(), before)
            self.assertGreaterEqual(len(histories), 1)

    def test_repeat_restore_does_not_duplicate_records(self) -> None:
        """Keep a repeated restore into one target idempotent.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Record counts stay stable.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            _, manifest = _archive_session(fixture)
            session, _ = _existing_session(fixture)
            _restore_into(fixture, manifest["archive_id"], session.session_id)
            counts = _record_count(fixture["root"], session)
            _restore_into(fixture, manifest["archive_id"], session.session_id)
            self.assertEqual(_record_count(fixture["root"], session), counts)

    def test_corrupt_archive_is_rejected_before_writing(self) -> None:
        """Refuse to restore from a tampered archive.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ArchiveError is raised and no target folder appears.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            _, manifest = _archive_session(fixture)
            _tamper(fixture, manifest)
            target_folder = fixture["store"].root / "corrupt1"
            with self.assertRaises(ArchiveError):
                _restore_into(fixture, manifest["archive_id"], "corrupt1")
            self.assertFalse(target_folder.exists())

    def test_archive_files_remain_unchanged_after_restore(self) -> None:
        """Leave archive bytes unchanged after a successful restore.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The archive still verifies and its digest is unchanged.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            _, manifest = _archive_session(fixture)
            service = ArchiveService(fixture["root"], fixture["store"].root)
            before, after = _restore_manifest(fixture, manifest["archive_id"])
            self.assertEqual(before, after)
            self.assertTrue(service.verify(manifest["archive_id"])["ok"])


def _assert_new_restore(case, fixture, original):
    """Restore into a new session and assert every invariant.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    fixture : dict
        Fixture records and stores.
    original : dict
        Original identifier sets.

    Returns
    -------
    None
        Restore assertions pass.
    """
    _, manifest = _archive_session(fixture)
    session = _restored_session(fixture, manifest["archive_id"])
    records = _session_records(fixture["root"], session)
    _assert_new_ids(case, records, original)
    _assert_references(case, records)
    _assert_revisions(case, fixture["root"], records["notes"][0])
    _assert_transfer(case, session, records["threads"][0])


def _restored_session(fixture, archive_id):
    """Restore an archive and load its target session.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.
    archive_id : str
        Archive identifier.

    Returns
    -------
    SessionRecord
        Restored session.
    """
    result = _restore_new(fixture, archive_id)
    return fixture["store"].load(result["target_session_id"])


def _restore_stores(root):
    """Build the global stores used by a restore.

    Parameters
    ----------
    root : pathlib.Path
        Research root.

    Returns
    -------
    tuple
        Note, source, and evidence stores.
    """
    return NoteStore(root), SourceStore(root), EvidenceStore(root)


def _scope_ids(store, record):
    """Return identifiers owned by one session scope.

    Parameters
    ----------
    store : object
        Global record store.
    record : SessionRecord
        Owning session.

    Returns
    -------
    set
        Record identifiers.
    """
    return _ids(store.list(record.session_id, status=None))


def _tamper(fixture, manifest):
    """Corrupt one archived PNG file.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.
    manifest : dict
        Archive manifest.

    Returns
    -------
    None
        The archive no longer verifies.
    """
    target = _first_png(fixture["root"], manifest["archive_id"])
    target.write_bytes(b"tampered")


def _restore_manifest(fixture, archive_id):
    """Return archive manifest bytes before and after a restore.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.
    archive_id : str
        Archive identifier.

    Returns
    -------
    tuple
        Bytes before and after the restore.
    """
    before = _manifest_bytes(fixture, archive_id)
    _restore_new(fixture, archive_id)
    return before, _manifest_bytes(fixture, archive_id)


def _restore_new(fixture, archive_id):
    """Restore an archive into a new session.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.
    archive_id : str
        Archive identifier.

    Returns
    -------
    dict
        Restore result.
    """
    return _restore_into(fixture, archive_id, None)


def _restore_into(fixture, archive_id, session_id):
    """Restore an archive into a target session.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.
    archive_id : str
        Archive identifier.
    session_id : str or None
        Target session identifier.

    Returns
    -------
    dict
        Restore result.
    """
    root = fixture["root"]
    service = ArchiveService(root, fixture["store"].root)
    notes, sources, evidence = _restore_stores(root)
    return service.restore(
        archive_id, session_id, None, notes, sources, evidence
    )


def _original_ids(fixture):
    """Return the live identifiers before archiving.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.

    Returns
    -------
    dict
        Identifier sets keyed by record type.
    """
    record = fixture["record"]
    result = {"notes": _scope_ids(fixture["notes"], record)}
    result["sources"] = _scope_ids(fixture["sources"], record)
    result["evidence"] = _scope_ids(fixture["evidence"], record)
    result["threads"] = _ids(ThreadStore(record.folder).list(status=None))
    return result


def _ids(records):
    """Return identifiers from a list of records.

    Parameters
    ----------
    records : list
        Record mappings.

    Returns
    -------
    set
        Record identifiers.
    """
    return {item["id"] for item in records}


def _session_records(root, session):
    """Load all restored records for a session.

    Parameters
    ----------
    root : pathlib.Path
        Research root.
    session : SessionRecord
        Restored session.

    Returns
    -------
    dict
        Records keyed by type.
    """
    return {
        "notes": NoteStore(root).list(session.session_id, status=None),
        "sources": SourceStore(root).list(session.session_id, status=None),
        "evidence": EvidenceStore(root).list(session.session_id, status=None),
        "threads": ThreadStore(session.folder).list(status=None),
    }


def _assert_new_ids(case, records, original):
    """Assert that every restored record has a new identifier.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    records : dict
        Restored records.
    original : dict
        Original identifier sets.

    Returns
    -------
    None
        Identifier assertions pass.
    """
    for kind in ("notes", "sources", "evidence", "threads"):
        case.assertFalse(_ids(records[kind]) & original[kind])


def _assert_references(case, records):
    """Assert that restored references point at new identifiers.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    records : dict
        Restored records.

    Returns
    -------
    None
        Reference assertions pass.
    """
    note = records["notes"][0]
    source = records["sources"][0]
    evidence = records["evidence"][0]
    thread = records["threads"][0]
    _assert_note_links(case, note, source, evidence)
    _assert_thread_links(case, note, source, thread)


def _assert_note_links(case, note, source, evidence):
    """Assert that a note links to restored source and evidence.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    note : dict
        Restored note.
    source : dict
        Restored source.
    evidence : dict
        Restored evidence.

    Returns
    -------
    None
        Link assertions pass.
    """
    case.assertIn(source["id"], note["source_ids"])
    case.assertIn(evidence["id"], note["evidence_ids"])
    case.assertEqual(evidence["source_id"], source["id"])


def _assert_thread_links(case, note, source, thread):
    """Assert that note and source point at the restored thread.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    note : dict
        Restored note.
    source : dict
        Restored source.
    thread : dict
        Restored thread.

    Returns
    -------
    None
        Thread assertions pass.
    """
    case.assertEqual(note["scope"]["thread_id"], thread["id"])
    case.assertEqual(source["occurrences"][0]["thread_id"], thread["id"])


def _assert_revisions(case, root, note):
    """Assert that note revisions were copied under the new identifier.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    root : pathlib.Path
        Research root.
    note : dict
        Restored note.

    Returns
    -------
    None
        Revision assertions pass.
    """
    revisions = NoteStore(root).revisions(note["id"])
    case.assertEqual([item["revision"] for item in revisions], [1])


def _assert_transfer(case, session, thread):
    """Assert that transfer thread references were remapped.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    session : SessionRecord
        Restored session.
    thread : dict
        Restored thread.

    Returns
    -------
    None
        Transfer assertions pass.
    """
    records = TransferStore(session.folder).list()
    case.assertEqual(records[0]["target_thread_id"], thread["id"])


def _existing_session(fixture):
    """Create an existing session with an active transcript.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.

    Returns
    -------
    tuple
        Existing session and its transcript text.
    """
    session = fixture["store"].create("Existing")
    before = '{"role": "user", "content": "old"}\n'
    session.transcript.write_text(before)
    return session, before


def _record_count(root, session):
    """Count restored records owned by a session.

    Parameters
    ----------
    root : pathlib.Path
        Research root.
    session : SessionRecord
        Session to count.

    Returns
    -------
    int
        Total global and thread record count.
    """
    records = _session_records(root, session)
    return sum(len(items) for items in records.values())


def _manifest_bytes(fixture, archive_id):
    """Read the archive manifest bytes.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.
    archive_id : str
        Archive identifier.

    Returns
    -------
    bytes
        Manifest content.
    """
    path = fixture["root"] / "archives" / archive_id / "manifest.json"
    return path.read_bytes()


if __name__ == "__main__":
    unittest.main()
