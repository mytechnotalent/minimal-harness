"""Complete archive snapshots of research sessions and their records."""

import copy
import json
import shutil
import time
import uuid
from pathlib import Path

from .atomic import append_text
from .atomic import read_json
from .atomic import rename_atomic
from .atomic import write_bytes_atomic
from .atomic import write_json_atomic
from .hashing import sha256_bytes
from .hashing import sha256_file
from .ids import IdMap
from .ids import new_id
from .ids import require_id
from .journal import Journal
from .locks import OperationLock
from .schemas import validate_record

ARCHIVE_PREFIX = "ar"
RESTORE_PREFIX = "rs"
HISTORY_PREFIX = "rh"
FORMAT_VERSION = 1
_MANIFEST = "manifest.json"
_DIGEST = "manifest.sha256"
_STEM_KINDS = frozenset(
    {"note", "source", "evidence_meta", "evidence_png", "tombstone"}
)
_ID_KINDS = (
    ("thread_meta", "thread", "th"),
    ("note", "note", "nt"),
    ("source", "source", "src"),
    ("evidence_meta", "evidence", "ev"),
    ("restored_history_meta", "restored_history", "rh"),
    ("tombstone", "tombstone", "th"),
)


class ArchiveError(RuntimeError):
    """Report an archive operation that cannot complete."""


class ArchiveService:
    """Archive and verify complete research session snapshots."""

    def __init__(self, research_root, sessions_root=None, fault_hook=None):
        """Prepare archive storage under a research root.

        Parameters
        ----------
        research_root : pathlib.Path or str
            Global research data root.
        sessions_root : pathlib.Path or str or None
            Session folder parent used by restore.
        fault_hook : collections.abc.Callable or None
            Optional crash-injection hook called with a point name.

        Returns
        -------
        None
            The archive, restore, and journal directories exist.
        """
        self.root = Path(research_root)
        self.fault_hook = fault_hook
        self.sessions_root = _sessions_path(sessions_root)
        self._prepare_storage()

    def _prepare_storage(self):
        """Create the archive, restore, and journal folders.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Storage paths are set and folders exist.
        """
        self.archives = self.root / "archives"
        self.staging = self.archives / ".staging"
        self.restores = self.root / "restores"
        self.purging = self.root / ".purging"
        self.journals = self.root / "journals"
        _ensure_dirs(self.archives, self.restores, self.journals)

    def archive_session(
        self, record, note_store, source_store, evidence_store
    ):
        """Archive a session, verify it, and delete its live data.

        Parameters
        ----------
        record : SessionRecord
            Session to archive.
        note_store : NoteStore or None
            Global note store.
        source_store : SourceStore or None
            Global source store.
        evidence_store : EvidenceStore or None
            Global evidence store.

        Returns
        -------
        dict
            Completed archive manifest.
        """
        archive_id, staging, paths = self._archive_inputs(
            record, note_store, source_store, evidence_store
        )
        journal = Journal(self.journals / f"archive-{archive_id}.json")
        with self._lock("archive"):
            return self._run_archive(
                record, paths, archive_id, staging, journal
            )

    def _archive_inputs(
        self, record, note_store, source_store, evidence_store
    ):
        """Allocate an archive identifier and collect live record paths.

        Parameters
        ----------
        record : SessionRecord
            Session to archive.
        note_store : NoteStore or None
            Global note store.
        source_store : SourceStore or None
            Global source store.
        evidence_store : EvidenceStore or None
            Global evidence store.

        Returns
        -------
        tuple
            Archive identifier, staging path, and global record paths.
        """
        archive_id = new_id(ARCHIVE_PREFIX)
        paths = _global_paths(
            record, note_store, source_store, evidence_store, self.root
        )
        return archive_id, self.staging / archive_id, paths

    def verify(self, archive_id):
        """Verify an archive manifest digest and every archived file.

        Parameters
        ----------
        archive_id : str
            Archive identifier.

        Returns
        -------
        dict
            Verification result with ``ok`` and ``errors`` fields.
        """
        require_id(archive_id, ARCHIVE_PREFIX)
        folder = self.archives / archive_id
        manifest = read_json(folder / _MANIFEST)
        return _verify(folder, manifest)

    def list(self):
        """Return completed archive manifests, newest first.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Archive manifests.
        """
        manifests = _read_manifests(self.archives)
        return sorted(
            manifests, key=lambda item: item.get("created_at", 0), reverse=True
        )

    def restore(
        self,
        archive_id,
        session_id=None,
        title=None,
        note_store=None,
        source_store=None,
        evidence_store=None,
    ):
        """Restore a verified archive into a session.

        Parameters
        ----------
        archive_id : str
            Archive identifier.
        session_id : str or None
            Existing session identifier, or ``None`` for a new session.
        title : str or None
            Title for a new session.
        note_store : NoteStore or None
            Global note store.
        source_store : SourceStore or None
            Global source store.
        evidence_store : EvidenceStore or None
            Global evidence store.

        Returns
        -------
        dict
            Restore result with target session and archive identifiers.
        """
        manifest = self._checked_manifest(archive_id)
        target = self._restore_target(session_id, archive_id)
        if _already_restored(target, archive_id):
            return _existing_result(target, archive_id)
        restore_id = new_id(RESTORE_PREFIX)
        idmap = _prepare_restore(self.restores, manifest, restore_id)
        self._start_restore(manifest, restore_id, target, title, idmap)
        return _restore_result(target, archive_id, restore_id)

    def _start_restore(self, manifest, restore_id, target, title, idmap):
        """Run one restore under lock and journal.

        Parameters
        ----------
        manifest : dict
            Verified archive manifest.
        restore_id : str
            Restore identifier.
        target : dict
            Target session description.
        title : str or None
            Title for a new session.
        idmap : IdMap
            Planned identifier mapping.

        Returns
        -------
        None
            The restore is committed.
        """
        journal = Journal(self.journals / f"restore-{restore_id}.json")
        with self._lock("restore"):
            self._run_restore(
                manifest, restore_id, target, title, idmap, journal
            )

    def _checked_manifest(self, archive_id):
        """Verify an archive and return its manifest.

        Parameters
        ----------
        archive_id : str
            Archive identifier.

        Returns
        -------
        dict
            Verified manifest.
        """
        _require_verified(self.verify(archive_id))
        return read_json(self.archives / archive_id / _MANIFEST)

    def _restore_target(self, session_id, archive_id):
        """Resolve the target session folder and existence.

        Parameters
        ----------
        session_id : str or None
            Existing session identifier, or ``None``.
        archive_id : str
            Archive identifier.

        Returns
        -------
        dict
            Target session description.
        """
        if self.sessions_root is None:
            raise ArchiveError("sessions root is required to restore")
        if session_id is None:
            return _new_target(self.sessions_root, archive_id)
        return _target(self.sessions_root, session_id, archive_id)

    def _run_restore(
        self, manifest, restore_id, target, title, idmap, journal
    ):
        """Stage and commit one restore operation.

        Parameters
        ----------
        manifest : dict
            Verified archive manifest.
        restore_id : str
            Restore identifier.
        target : dict
            Target session description.
        title : str or None
            Title for a new session.
        idmap : IdMap
            Planned identifier mapping.
        journal : Journal
            Operation journal.

        Returns
        -------
        None
            The restore is committed.
        """
        staging = self.restores / "staging" / restore_id
        journal.write("staging", **_restore_journal(manifest, target, idmap))
        try:
            self._stage_and_commit(manifest, restore_id, target, title, idmap)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        journal.remove()

    def _stage_and_commit(self, manifest, restore_id, target, title, idmap):
        """Stage and commit a restore, recording each state.

        Parameters
        ----------
        manifest : dict
            Verified archive manifest.
        restore_id : str
            Restore identifier.
        target : dict
            Target session description.
        title : str or None
            Title for a new session.
        idmap : IdMap
            Planned identifier mapping.

        Returns
        -------
        None
            The restore is committed.
        """
        archive = self.archives / manifest["archive_id"]
        staging = self.restores / "staging" / restore_id
        _stage_restore(staging, archive, manifest, target, title, idmap)
        self._fault("restore_staged")
        self._finish_restore(manifest, restore_id, target, staging, idmap)

    def _finish_restore(self, manifest, restore_id, target, staging, idmap):
        """Commit a staged restore and record its states.

        Parameters
        ----------
        manifest : dict
            Verified archive manifest.
        restore_id : str
            Restore identifier.
        target : dict
            Target session description.
        staging : pathlib.Path
            Restore staging folder.
        idmap : IdMap
            Planned identifier mapping.

        Returns
        -------
        None
            The restore is committed.
        """
        self._write_journal_state(
            restore_id, "committing", manifest, target, idmap
        )
        _commit_restore(self.root, target, staging)
        self._write_journal_state(
            restore_id, "committed", manifest, target, idmap
        )
        self._fault("restore_committed")

    def _write_journal_state(self, restore_id, state, manifest, target, idmap):
        """Write one restore journal state.

        Parameters
        ----------
        restore_id : str
            Restore identifier.
        state : str
            Operation state.
        manifest : dict
            Verified archive manifest.
        target : dict
            Target session description.
        idmap : IdMap
            Planned identifier mapping.

        Returns
        -------
        None
            The journal is updated.
        """
        journal = Journal(self.journals / f"restore-{restore_id}.json")
        journal.write(state, **_restore_journal(manifest, target, idmap))

    def _lock(self, operation):
        """Return an operation lock for this research root.

        Parameters
        ----------
        operation : str
            Operation name.

        Returns
        -------
        OperationLock
            Lock for the operation.
        """
        return OperationLock(self.root / "operation.lock", operation)

    def _fault(self, point):
        """Invoke the configured fault hook.

        Parameters
        ----------
        point : str
            Fault injection point name.

        Returns
        -------
        None
            The hook returns normally or raises.
        """
        if self.fault_hook is not None:
            self.fault_hook(point)

    def _run_archive(self, record, paths, archive_id, staging, journal):
        """Execute an archive with journaling and fault points.

        Parameters
        ----------
        record : SessionRecord
            Session to archive.
        paths : list
            Global record paths.
        archive_id : str
            Archive identifier.
        staging : pathlib.Path
            Staging folder.
        journal : Journal
            Operation journal.

        Returns
        -------
        dict
            Completed manifest.
        """
        journal.write("staging", **_archive_journal(record, paths, archive_id))
        try:
            _run_archive_steps(
                self, staging, record, paths, archive_id, journal
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return _complete_archive(journal, self.archives / archive_id)

    def purge(self, archive_id):
        """Irreversibly purge one archive with a rename-first step.

        Parameters
        ----------
        archive_id : str
            Archive identifier.

        Returns
        -------
        None
            The archive is renamed and deleted.
        """
        require_id(archive_id, ARCHIVE_PREFIX)
        folder = self.archives / archive_id
        if not folder.exists():
            raise FileNotFoundError(archive_id)
        journal = Journal(self.journals / f"purge-{archive_id}.json")
        with self._lock("purge"):
            self._run_purge(archive_id, folder, journal)

    def _run_purge(self, archive_id, folder, journal):
        """Rename and delete one archive while journaling each state.

        Parameters
        ----------
        archive_id : str
            Archive identifier.
        folder : pathlib.Path
            Archive folder.
        journal : Journal
            Operation journal.

        Returns
        -------
        None
            The archive is deleted.
        """
        journal.write("renaming", operation="purge", archive_id=archive_id)
        rename_atomic(folder, self.purging / archive_id)
        self._fault("purge_renamed")
        journal.write("renamed")
        shutil.rmtree(self.purging / archive_id)
        self._fault("purge_deleted")
        journal.remove()

    def recover(self):
        """Resume or roll back incomplete journaled operations.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Every recoverable journal is handled.
        """
        with self._lock("recover"):
            for path in sorted(self.journals.glob("*.json")):
                _recover_one(self, path)

    def _recover_archive(self, data, path):
        """Finish or roll back an interrupted archive.

        Parameters
        ----------
        data : dict
            Archive journal data.
        path : pathlib.Path
            Journal path.

        Returns
        -------
        None
            The archive state is reconciled.
        """
        folder = self.archives / data["archive_id"]
        staging = self.staging / data["archive_id"]
        if folder.exists():
            _delete_journal_live(data)
        else:
            shutil.rmtree(staging, ignore_errors=True)
        path.unlink(missing_ok=True)

    def _recover_restore(self, data, path):
        """Finish or roll back an interrupted restore.

        Parameters
        ----------
        data : dict
            Restore journal data.
        path : pathlib.Path
            Journal path.

        Returns
        -------
        None
            The restore state is reconciled.
        """
        staging = self.restores / "staging" / data["restore_id"]
        if data.get("state") == "committing" and staging.exists():
            _resume_commit(self, data, staging)
        shutil.rmtree(staging, ignore_errors=True)
        path.unlink(missing_ok=True)

    def _recover_purge(self, data, path):
        """Finish an interrupted purge.

        Parameters
        ----------
        data : dict
            Purge journal data.
        path : pathlib.Path
            Journal path.

        Returns
        -------
        None
            The purge state is reconciled.
        """
        archive_id = data["archive_id"]
        purging = self.purging / archive_id
        archive = self.archives / archive_id
        _purge_remaining(purging, archive)
        path.unlink(missing_ok=True)


def _store_archive(staging, record, paths, archive_id, archives, fault):
    """Stage, verify, and rename one archive.

    Parameters
    ----------
    staging : pathlib.Path
        Staging directory.
    record : SessionRecord
        Session to archive.
    paths : list
        Global record paths.
    archive_id : str
        New archive identifier.
    archives : pathlib.Path
        Completed archive parent.
    fault : collections.abc.Callable
        Fault injection callback.

    Returns
    -------
    None
        The archive is verified and renamed.
    """
    manifest = _stage_archive(staging, record, paths, archive_id)
    _require_verified(_verify(staging, manifest))
    fault("archive_staged")
    rename_atomic(staging, archives / archive_id)


def _stage_archive(staging, record, paths, archive_id):
    """Copy a session and its global records into staging.

    Parameters
    ----------
    staging : pathlib.Path
        Staging directory.
    record : SessionRecord
        Session to archive.
    paths : list
        Global record paths to copy.
    archive_id : str
        New archive identifier.

    Returns
    -------
    dict
        Completed manifest before the final digest is written.
    """
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copytree(record.folder, staging / "session")
    _copy_globals(staging, paths)
    manifest = _build_manifest(archive_id, record, staging)
    _finish_manifest(staging, manifest)
    return manifest


def _copy_globals(staging, paths):
    """Copy global record files into the archive staging tree.

    Parameters
    ----------
    staging : pathlib.Path
        Staging directory.
    paths : list
        Global record paths.

    Returns
    -------
    None
        Files are copied under the ``global`` folder.
    """
    for path in paths:
        target = staging / "global" / _relative(path)
        write_bytes_atomic(target, Path(path).read_bytes())


def _relative(path):
    """Strip the research root from a global record path.

    Parameters
    ----------
    path : pathlib.Path or str
        Path inside the research root.

    Returns
    -------
    pathlib.Path
        Relative path.
    """
    parts = Path(path).parts
    markers = ("notes", "sources", "evidence", "tombstones")
    for index, part in enumerate(parts):
        if part in markers:
            return Path(*parts[index:])
    return Path(Path(path).name)


def _build_manifest(archive_id, record, staging):
    """Build a manifest describing every staged file.

    Parameters
    ----------
    archive_id : str
        Archive identifier.
    record : SessionRecord
        Archived session.
    staging : pathlib.Path
        Staging directory.

    Returns
    -------
    dict
        Manifest with file entries, counts, and identifiers.
    """
    files = _file_entries(staging)
    manifest = _manifest_base(archive_id, record)
    manifest["files"] = files
    manifest["counts"] = _counts(files)
    manifest["id_index"] = _id_index(files)
    return manifest


def _manifest_base(archive_id, record):
    """Build the identity and status fields of a manifest.

    Parameters
    ----------
    archive_id : str
        Archive identifier.
    record : SessionRecord
        Archived session.

    Returns
    -------
    dict
        Partial manifest.
    """
    manifest = {
        "archive_id": archive_id,
        "format_version": FORMAT_VERSION,
        "original_session_id": record.session_id,
        "original_session_meta": _session_meta(record),
    }
    manifest.update(_manifest_state())
    return manifest


def _purge_live(record, paths, archive_folder):
    """Delete live session data after a successful archive.

    Parameters
    ----------
    record : SessionRecord
        Archived session.
    paths : list
        Global record paths to remove.
    archive_folder : pathlib.Path
        Completed archive folder.

    Returns
    -------
    dict
        Completed manifest.
    """
    _delete_live(record, paths)
    return read_json(archive_folder / _MANIFEST)


def _manifest_state():
    """Build the timestamp, status, and index fields of a manifest.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        State fields.
    """
    state = {"created_at": time.time(), "completed_at": None}
    state.update(_manifest_flags())
    return state


def _manifest_flags():
    """Build the status and empty index fields of a manifest.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Status and index fields.
    """
    return {
        "status": "staging",
        "verification": {"status": "pending", "checked_at": None},
        "counts": {},
        "files": [],
        "id_index": {},
    }


def _session_meta(record):
    """Read the archived session metadata when it exists.

    Parameters
    ----------
    record : SessionRecord
        Archived session.

    Returns
    -------
    dict
        Session metadata or an empty mapping.
    """
    if not record.meta.exists():
        return {}
    return read_json(record.meta)


def _file_entries(staging):
    """List every staged file with kind, size, hash, and record id.

    Parameters
    ----------
    staging : pathlib.Path
        Staging directory.

    Returns
    -------
    list
        File entry mappings.
    """
    folders = staging / "global"
    paths = [staging / "session"]
    paths.extend([folders] if folders.exists() else [])
    entries = []
    for base in paths:
        entries.extend(_walk_entries(base))
    return sorted(entries, key=lambda entry: entry["path"])


def _walk_entries(base):
    """Build entries for every file under a base path.

    Parameters
    ----------
    base : pathlib.Path
        Folder to walk.

    Returns
    -------
    list
        File entry mappings.
    """
    if not base.exists():
        return []
    return [_entry(base, path) for path in base.rglob("*") if path.is_file()]


def _entry(base, path):
    """Build one file entry.

    Parameters
    ----------
    base : pathlib.Path
        Walk root.
    path : pathlib.Path
        File to describe.

    Returns
    -------
    dict
        File entry mapping.
    """
    relative = path.relative_to(base.parent)
    kind = _kind(relative)
    entry = {"path": str(relative), "kind": kind, "size": path.stat().st_size}
    entry["sha256"] = sha256_file(path)
    entry["record_id"] = _record_id(relative, kind)
    return entry


def _kind(relative):
    """Return the record kind of an archived file path.

    Parameters
    ----------
    relative : pathlib.Path
        Path relative to the staging root.

    Returns
    -------
    str
        Record kind.
    """
    parts = relative.parts
    if parts[0] == "global":
        return _global_kind(parts[1:])
    return _session_kind(parts[1:])


def _session_kind(parts):
    """Return the kind of a session-tree file.

    Parameters
    ----------
    parts : tuple
        Path parts after the session folder.

    Returns
    -------
    str
        Record kind.
    """
    if parts == ("meta.json",):
        return "session_meta"
    if parts == ("transcript.jsonl",):
        return "primary_transcript"
    if _thread_file(parts):
        return _thread_kind(parts)
    return _session_rest(parts)


def _thread_kind(parts):
    """Return the kind of a thread metadata or transcript file.

    Parameters
    ----------
    parts : tuple
        Path parts after the session folder.

    Returns
    -------
    str
        Record kind.
    """
    return (
        "thread_transcript" if parts[-1].endswith(".jsonl") else "thread_meta"
    )


def _session_rest(parts):
    """Return the kind of a non-thread session-tree file.

    Parameters
    ----------
    parts : tuple
        Path parts after the session folder.

    Returns
    -------
    str
        Record kind.
    """
    if parts[:2] == ("research", "transfers.jsonl"):
        return "transfer"
    if parts[0] == "restored" and len(parts) == 3:
        return _restored_kind(parts[-1])
    if parts[:2] == ("research", "proposals"):
        return "proposal"
    return "session_file"


def _thread_file(parts):
    """Return whether a path is a research thread file.

    Parameters
    ----------
    parts : tuple
        Path parts after the session folder.

    Returns
    -------
    bool
        ``True`` for a thread metadata or transcript file.
    """
    return (
        len(parts) == 4
        and parts[:2] == ("research", "threads")
        and parts[-1] in ("meta.json", "transcript.jsonl")
    )


def _restored_kind(name):
    """Return the kind of a restored history file.

    Parameters
    ----------
    name : str
        File name.

    Returns
    -------
    str
        Record kind.
    """
    return (
        "restored_history_transcript"
        if name.endswith(".jsonl")
        else "restored_history_meta"
    )


def _global_kind(parts):
    """Return the kind of a global record file.

    Parameters
    ----------
    parts : tuple
        Path parts after the global folder.

    Returns
    -------
    str
        Record kind.
    """
    if parts[0] == "notes":
        return _note_kind(parts)
    if parts[0] == "evidence":
        return _evidence_kind(parts)
    return _global_simple(parts[0])


def _note_kind(parts):
    """Return the kind of a note file.

    Parameters
    ----------
    parts : tuple
        Path parts after the global folder.

    Returns
    -------
    str
        Record kind.
    """
    return "note_revision" if parts[1] == "revisions" else "note"


def _evidence_kind(parts):
    """Return the kind of an evidence file.

    Parameters
    ----------
    parts : tuple
        Path parts after the global folder.

    Returns
    -------
    str
        Record kind.
    """
    return "evidence_png" if parts[-1].endswith(".png") else "evidence_meta"


def _global_simple(head):
    """Return the kind of a simple global file group.

    Parameters
    ----------
    head : str
        First path part after the global folder.

    Returns
    -------
    str
        Record kind.
    """
    return {"sources": "source", "tombstones": "tombstone"}.get(
        head, "global_file"
    )


def _record_id(relative, kind):
    """Return the original record identifier for an archived file.

    Parameters
    ----------
    relative : pathlib.Path
        Path relative to the staging root.
    kind : str
        Record kind.

    Returns
    -------
    str or None
        Record identifier.
    """
    if kind in ("thread_meta", "thread_transcript"):
        return relative.parts[-2]
    return _id_for_kind(relative, kind)


def _id_for_kind(relative, kind):
    """Return the record identifier for non-thread archive kinds.

    Parameters
    ----------
    relative : pathlib.Path
        Path relative to the staging root.
    kind : str
        Record kind.

    Returns
    -------
    str or None
        Record identifier.
    """
    if kind.startswith("restored_history"):
        return relative.parts[-2]
    if kind == "note_revision":
        return relative.parts[-2]
    if kind in _STEM_KINDS:
        return relative.stem
    return None


def _counts(files):
    """Count archived files by record kind.

    Parameters
    ----------
    files : list
        File entries.

    Returns
    -------
    dict
        Counts keyed by kind.
    """
    counts = {}
    for entry in files:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    return counts


def _id_index(files):
    """Index archived record identifiers to their file paths.

    Parameters
    ----------
    files : list
        File entries.

    Returns
    -------
    dict
        Kind to identifier to path list mapping.
    """
    index = {}
    for entry in files:
        record_id = entry.get("record_id")
        if record_id is None:
            continue
        bucket = index.setdefault(entry["kind"], {}).setdefault(record_id, [])
        bucket.append(entry["path"])
    return index


def _finish_manifest(staging, manifest):
    """Mark a manifest complete and write its separate digest.

    Parameters
    ----------
    staging : pathlib.Path
        Staging directory.
    manifest : dict
        Manifest to finalize.

    Returns
    -------
    None
        The manifest and digest files are written.
    """
    manifest["status"] = "complete"
    manifest["completed_at"] = time.time()
    manifest["verification"] = _verification_stamp(manifest)
    _write_manifest(staging, manifest)


def _verification_stamp(manifest):
    """Build the verification field recorded after a clean check.

    Parameters
    ----------
    manifest : dict
        Manifest being completed.

    Returns
    -------
    dict
        Verification metadata.
    """
    return {
        "status": "verified",
        "checked_at": time.time(),
        "files": len(manifest.get("files", [])),
    }


def _write_manifest(staging, manifest):
    """Validate and write a manifest and its digest.

    Parameters
    ----------
    staging : pathlib.Path
        Staging directory.
    manifest : dict
        Manifest to write.

    Returns
    -------
    None
        Both files are written atomically.
    """
    validate_record("archive", manifest)
    write_json_atomic(staging / _MANIFEST, manifest)
    digest = sha256_file(staging / _MANIFEST)
    write_bytes_atomic(staging / _DIGEST, (digest + "\n").encode("utf-8"))


def _verify(folder, manifest):
    """Verify a manifest digest and every listed file.

    Parameters
    ----------
    folder : pathlib.Path
        Archive folder.
    manifest : dict
        Parsed manifest.

    Returns
    -------
    dict
        Verification result with ``ok`` and ``errors`` fields.
    """
    errors = []
    digest = _check_digest(folder, errors)
    for entry in manifest.get("files", []):
        _check_entry(folder, entry, errors)
    counts = _counts(manifest.get("files", []))
    if counts != manifest.get("counts"):
        errors.append("manifest counts do not match files")
    return _result(manifest, digest, errors)


def _check_digest(folder, errors):
    """Check the manifest digest file.

    Parameters
    ----------
    folder : pathlib.Path
        Archive folder.
    errors : list
        Error accumulator.

    Returns
    -------
    str
        Computed manifest digest.
    """
    digest = sha256_file(folder / _MANIFEST)
    stored = _stored_digest(folder)
    if stored != digest:
        errors.append("manifest digest mismatch")
    return digest


def _stored_digest(folder):
    """Read the stored manifest digest.

    Parameters
    ----------
    folder : pathlib.Path
        Archive folder.

    Returns
    -------
    str
        Stored digest or an empty string.
    """
    path = folder / _DIGEST
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _check_entry(folder, entry, errors):
    """Check one archived file against its manifest entry.

    Parameters
    ----------
    folder : pathlib.Path
        Archive folder.
    entry : dict
        File entry.
    errors : list
        Error accumulator.

    Returns
    -------
    None
        Any mismatch is appended to the errors.
    """
    path = folder / entry["path"]
    if not path.exists():
        errors.append("missing file: " + entry["path"])
    elif path.stat().st_size != entry["size"]:
        errors.append("size mismatch: " + entry["path"])
    elif sha256_file(path) != entry["sha256"]:
        errors.append("hash mismatch: " + entry["path"])


def _result(manifest, digest, errors):
    """Build a verification result mapping.

    Parameters
    ----------
    manifest : dict
        Verified manifest.
    digest : str
        Computed manifest digest.
    errors : list
        Verification errors.

    Returns
    -------
    dict
        Verification result.
    """
    return {
        "archive_id": manifest.get("archive_id"),
        "ok": not errors,
        "manifest_digest": digest,
        "errors": list(errors),
    }


def _require_verified(result):
    """Raise when a staging verification fails.

    Parameters
    ----------
    result : dict
        Verification result.

    Returns
    -------
    None
        The archive passed verification.
    """
    if not result["ok"]:
        raise ArchiveError("; ".join(result["errors"]))


def _global_paths(record, note_store, source_store, evidence_store, root):
    """Collect the live global record paths owned by a session.

    Parameters
    ----------
    record : SessionRecord
        Session owning the records.
    note_store : NoteStore or None
        Global note store.
    source_store : SourceStore or None
        Global source store.
    evidence_store : EvidenceStore or None
        Global evidence store.
    root : pathlib.Path
        Global research root.

    Returns
    -------
    list
        Live global record paths.
    """
    paths = []
    if note_store is not None:
        paths.extend(_note_paths(note_store, record.session_id))
    if source_store is not None:
        paths.extend(_source_paths(source_store, record.session_id))
    if evidence_store is not None:
        paths.extend(_evidence_paths(evidence_store, record.session_id))
    return paths + _tombstone_paths(root, record.session_id)


def _note_paths(store, session_id):
    """Collect note and revision paths for one session.

    Parameters
    ----------
    store : NoteStore
        Global note store.
    session_id : str
        Session scope.

    Returns
    -------
    list
        Note and revision paths.
    """
    paths = []
    for note in store.list(session_id, status=None):
        paths.append(store._path(note["id"]))
        paths.extend(_revision_paths(store, note["id"]))
    return paths


def _revision_paths(store, note_id):
    """Return the revision file paths for one note.

    Parameters
    ----------
    store : NoteStore
        Global note store.
    note_id : str
        Note identifier.

    Returns
    -------
    list
        Revision paths.
    """
    folder = store.revision_root / note_id
    return sorted(folder.glob("r*.json"))


def _source_paths(store, session_id):
    """Collect source paths for one session.

    Parameters
    ----------
    store : SourceStore
        Global source store.
    session_id : str
        Session scope.

    Returns
    -------
    list
        Source paths.
    """
    return [
        store._path(item["id"]) for item in store.list(session_id, status=None)
    ]


def _evidence_paths(store, session_id):
    """Collect evidence metadata and PNG paths for one session.

    Parameters
    ----------
    store : EvidenceStore
        Global evidence store.
    session_id : str
        Session scope.

    Returns
    -------
    list
        Evidence paths.
    """
    paths = []
    for record in store.list(session_id, status=None):
        paths.extend([store._meta_path(record), store._png_path(record)])
    return paths


def _tombstone_paths(root, session_id):
    """Collect tombstone paths for one session.

    Parameters
    ----------
    root : pathlib.Path
        Global research root.
    session_id : str
        Session scope.

    Returns
    -------
    list
        Tombstone paths.
    """
    folder = Path(root) / "tombstones" / "threads"
    return [
        path
        for path in sorted(folder.glob("*.json"))
        if _tombstone_matches(path, session_id)
    ]


def _tombstone_matches(path, session_id):
    """Return whether a tombstone belongs to a session.

    Parameters
    ----------
    path : pathlib.Path
        Tombstone file.
    session_id : str
        Session scope.

    Returns
    -------
    bool
        ``True`` when the tombstone matches.
    """
    try:
        return read_json(path).get("session_id") == session_id
    except (OSError, ValueError):
        return False


def _delete_live(record, paths):
    """Delete a session folder and its live global records.

    Parameters
    ----------
    record : SessionRecord
        Session to delete.
    paths : list
        Global record paths to remove.

    Returns
    -------
    None
        Live data is removed.
    """
    for path in paths:
        Path(path).unlink(missing_ok=True)
    shutil.rmtree(record.folder, ignore_errors=True)


def _read_manifests(folder):
    """Read every complete archive manifest.

    Parameters
    ----------
    folder : pathlib.Path
        Archive parent folder.

    Returns
    -------
    list
        Parsed manifests.
    """
    if not folder.exists():
        return []
    paths = [path / _MANIFEST for path in folder.iterdir() if path.is_dir()]
    return [read_json(path) for path in paths if path.exists()]


def _new_target(sessions_root, archive_id):
    """Build a new-session restore target.

    Parameters
    ----------
    sessions_root : pathlib.Path
        Session folder parent.
    archive_id : str
        Archive identifier.

    Returns
    -------
    dict
        Target session description.
    """
    session_id = uuid.uuid4().hex[:12]
    return _target_dict(
        session_id, sessions_root / session_id, False, archive_id
    )


def _target(sessions_root, session_id, archive_id):
    """Build an existing-session restore target.

    Parameters
    ----------
    sessions_root : pathlib.Path
        Session folder parent.
    session_id : str
        Existing session identifier.
    archive_id : str
        Archive identifier.

    Returns
    -------
    dict
        Target session description.
    """
    folder = sessions_root / session_id
    return _target_dict(session_id, folder, folder.exists(), archive_id)


def _target_dict(session_id, folder, existing, archive_id):
    """Build a target session description mapping.

    Parameters
    ----------
    session_id : str
        Session identifier.
    folder : pathlib.Path
        Session folder.
    existing : bool
        Whether the folder already exists.
    archive_id : str
        Archive identifier.

    Returns
    -------
    dict
        Target session description.
    """
    return {
        "session_id": session_id,
        "folder": folder,
        "existing": existing,
        "archive_id": archive_id,
    }


def _marker_path(folder, archive_id):
    """Return the restore marker path for an archive.

    Parameters
    ----------
    folder : pathlib.Path
        Session folder.
    archive_id : str
        Archive identifier.

    Returns
    -------
    pathlib.Path
        Marker path.
    """
    return Path(folder) / "research" / "restores" / f"{archive_id}.json"


def _already_restored(target, archive_id):
    """Return whether an archive was already restored to a target.

    Parameters
    ----------
    target : dict
        Target session description.
    archive_id : str
        Archive identifier.

    Returns
    -------
    bool
        ``True`` when the target holds a restore marker.
    """
    if not target["existing"]:
        return False
    return _marker_path(target["folder"], archive_id).exists()


def _write_marker(folder, archive_id, restore_id):
    """Write the marker that makes repeat restores idempotent.

    Parameters
    ----------
    folder : pathlib.Path
        Staged session folder.
    archive_id : str
        Archive identifier.
    restore_id : str
        Restore identifier.

    Returns
    -------
    None
        The marker is written.
    """
    record = {"archive_id": archive_id, "restore_id": restore_id}
    record["restored_at"] = time.time()
    write_json_atomic(_marker_path(folder, archive_id), record)


def _existing_result(target, archive_id):
    """Build a result for an already-completed restore.

    Parameters
    ----------
    target : dict
        Target session description.
    archive_id : str
        Archive identifier.

    Returns
    -------
    dict
        Existing restore result.
    """
    record = read_json(_marker_path(target["folder"], archive_id))
    record["target_session_id"] = target["session_id"]
    record["existing"] = True
    record["folder"] = str(target["folder"])
    return record


def _restore_result(target, archive_id, restore_id):
    """Build the result returned by a new restore.

    Parameters
    ----------
    target : dict
        Target session description.
    archive_id : str
        Archive identifier.
    restore_id : str
        Restore identifier.

    Returns
    -------
    dict
        Restore result.
    """
    return {
        "archive_id": archive_id,
        "restore_id": restore_id,
        "target_session_id": target["session_id"],
        "existing": target["existing"],
        "folder": str(target["folder"]),
    }


def _prepare_restore(restores, manifest, restore_id):
    """Plan identifiers and persist the mapping before any write.

    Parameters
    ----------
    restores : pathlib.Path
        Restore storage folder.
    manifest : dict
        Verified archive manifest.
    restore_id : str
        Restore identifier.

    Returns
    -------
    IdMap
        Planned identifier mapping.
    """
    idmap = _plan_ids(manifest, restore_id)
    idmap.save(restores / restore_id / "id_map.json")
    return idmap


def _plan_ids(manifest, restore_id):
    """Allocate restored identifiers for every indexed record.

    Parameters
    ----------
    manifest : dict
        Verified archive manifest.
    restore_id : str
        Restore identifier.

    Returns
    -------
    IdMap
        Planned identifier mapping.
    """
    idmap = IdMap(restore_id)
    for archived, logical, prefix in _ID_KINDS:
        _plan_kind(idmap, manifest, archived, logical, prefix)
    return idmap


def _plan_kind(idmap, manifest, archived, logical, prefix):
    """Allocate identifiers for one archived record kind.

    Parameters
    ----------
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.
    archived : str
        Archived file kind.
    logical : str
        Logical record kind used by mappings.
    prefix : str
        Identifier prefix.

    Returns
    -------
    None
        New identifiers are recorded.
    """
    originals = manifest.get("id_index", {}).get(archived, {})
    for original in originals:
        idmap.new(logical, prefix, original)


def _stage_restore(staging, archive, manifest, target, title, idmap):
    """Stage a full session and global record restore.

    Parameters
    ----------
    staging : pathlib.Path
        Restore staging folder.
    archive : pathlib.Path
        Archive folder.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    title : str or None
        Title for a new session.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        Staged files are written.
    """
    _stage_session(
        staging / "session", archive, manifest, target, title, idmap
    )
    _stage_global(
        staging / "global", archive / "global", target, idmap, manifest
    )


def _stage_session(session, archive, manifest, target, title, idmap):
    """Stage the session tree for restore.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    archive : pathlib.Path
        Archive folder.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    title : str or None
        Title for a new session.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        Session files are staged.
    """
    session.mkdir(parents=True, exist_ok=True)
    _stage_primary(
        session, archive / "session", manifest, target, title, idmap
    )
    _stage_threads(session, archive / "session", manifest, target, idmap)
    _stage_histories(session, archive / "session", manifest, target, idmap)
    _stage_transfers(session, archive / "session", manifest, target, idmap)
    _write_marker(session, manifest["archive_id"], idmap.restore_id)


def _stage_primary(session, source, manifest, target, title, idmap):
    """Stage the primary transcript or a read-only restored history.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    source : pathlib.Path
        Archived session folder.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    title : str or None
        Title for a new session.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        Primary history is staged.
    """
    if target["existing"]:
        _stage_restored_primary(session, source, manifest, target, idmap)
        return
    _write_session_meta(session, manifest, target, title)
    _copy_primary(session, source)


def _write_session_meta(session, manifest, target, title):
    """Write the metadata for a restored new session.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    title : str or None
        Title for the session.

    Returns
    -------
    None
        Metadata is written.
    """
    meta = _session_meta_doc(manifest, target, title)
    write_json_atomic(session / "meta.json", meta)


def _copy_primary(session, source):
    """Copy the archived primary transcript into a new session.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    source : pathlib.Path
        Archived session folder.

    Returns
    -------
    None
        The transcript is written.
    """
    data = _read_bytes(source / "transcript.jsonl")
    write_bytes_atomic(session / "transcript.jsonl", data)


def _stage_restored_primary(session, source, manifest, target, idmap):
    """Store a primary transcript as a read-only restored history.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    source : pathlib.Path
        Archived session folder.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        The restored history is staged.
    """
    data = _read_bytes(source / "transcript.jsonl")
    history_id = new_id(HISTORY_PREFIX)
    record = _primary_history(
        manifest, target, idmap.restore_id, history_id, data
    )
    folder = session / "restored" / history_id
    write_json_atomic(folder / "meta.json", record)
    write_bytes_atomic(folder / "transcript.jsonl", data)


def _sessions_path(sessions_root):
    """Return a resolved optional sessions root.

    Parameters
    ----------
    sessions_root : pathlib.Path or str or None
        Session folder parent.

    Returns
    -------
    pathlib.Path or None
        Sessions root or ``None``.
    """
    return None if sessions_root is None else Path(sessions_root)


def _session_meta_doc(manifest, target, title):
    """Build metadata for a restored new session.

    Parameters
    ----------
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    title : str or None
        Title for the session.

    Returns
    -------
    dict
        Session metadata.
    """
    original = manifest.get("original_session_meta", {})
    meta = {
        "id": target["session_id"],
        "title": title or original.get("title") or "Restored session",
    }
    meta["kind"] = original.get("kind", "session")
    meta.update(_session_meta_rest(manifest))
    return meta


def _session_meta_rest(manifest):
    """Build timestamps and provenance for a restored session.

    Parameters
    ----------
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    dict
        Timestamp and provenance fields.
    """
    now = time.time()
    return {
        "created": now,
        "updated": now,
        "restored_from_archive": manifest["archive_id"],
        "original_session_id": manifest["original_session_id"],
    }


def _history_identity_rest(manifest, restore_id):
    """Build remaining identity fields for a restored history.

    Parameters
    ----------
    manifest : dict
        Verified archive manifest.
    restore_id : str
        Restore identifier.

    Returns
    -------
    dict
        Identity fields.
    """
    original = manifest.get("original_session_meta", {})
    return {
        "restore_id": restore_id,
        "original_session_id": manifest["original_session_id"],
        "original_title": original.get("title", ""),
    }


def _write_thread_files(folder, record, source):
    """Write one thread metadata and transcript pair.

    Parameters
    ----------
    folder : pathlib.Path
        Destination thread folder.
    record : dict
        Thread metadata.
    source : pathlib.Path
        Archived thread folder.

    Returns
    -------
    None
        Both files are written.
    """
    write_json_atomic(folder / "meta.json", record)
    write_bytes_atomic(
        folder / "transcript.jsonl", _read_bytes(source / "transcript.jsonl")
    )


def _transfer_links(original, target, idmap):
    """Build the remapped thread links of a transfer.

    Parameters
    ----------
    original : dict
        Archived transfer.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Session and thread link fields.
    """
    record = {"session_id": target["session_id"]}
    record["source_thread_id"] = _remap(
        original.get("source_thread_id"), "thread", idmap
    )
    record["target_thread_id"] = _remap(
        original.get("target_thread_id"), "thread", idmap
    )
    return record


def _note_refs(original, idmap):
    """Build the remapped source and evidence references of a note.

    Parameters
    ----------
    original : dict
        Archived note.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Reference fields.
    """
    return {
        "source_ids": _remap_list(
            original.get("source_ids", []), "source", idmap
        ),
        "evidence_ids": _remap_list(
            original.get("evidence_ids", []), "evidence", idmap
        ),
    }


def _source_occurrences(original, idmap):
    """Build restored occurrences for one source.

    Parameters
    ----------
    original : dict
        Archived source.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    list
        Restored occurrences.
    """
    return [
        _source_occurrence(item, idmap)
        for item in original.get("occurrences", [])
    ]


def _write_evidence_files(folder, evidence_id, record, source):
    """Write one evidence metadata and PNG pair.

    Parameters
    ----------
    folder : pathlib.Path
        Destination evidence folder.
    evidence_id : str
        New evidence identifier.
    record : dict
        Evidence metadata.
    source : pathlib.Path
        Archived metadata path.

    Returns
    -------
    None
        Both files are written.
    """
    write_json_atomic(folder / f"{evidence_id}.json", record)
    write_bytes_atomic(
        folder / f"{evidence_id}.png", _read_bytes(source.with_suffix(".png"))
    )


def _tombstone_links(original, idmap):
    """Build the remapped surviving links of a tombstone.

    Parameters
    ----------
    original : dict
        Archived tombstone.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Link fields.
    """
    record = {
        "note_ids": _remap_list(original.get("note_ids", []), "note", idmap)
    }
    record.update(_tombstone_more_links(original, idmap))
    return record


def _tombstone_more_links(original, idmap):
    """Build remaining tombstone link fields.

    Parameters
    ----------
    original : dict
        Archived tombstone.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Link fields.
    """
    record = {"source_ids": _source_links(original, idmap)}
    record.update(_tombstone_record_links(original, idmap))
    return record


def _source_links(original, idmap):
    """Build remapped source links.

    Parameters
    ----------
    original : dict
        Archived record with ``source_ids``.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    list
        Restored source identifiers.
    """
    return _remap_list(original.get("source_ids", []), "source", idmap)


def _tombstone_record_links(original, idmap):
    """Build evidence and transfer tombstone links.

    Parameters
    ----------
    original : dict
        Archived tombstone.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Link fields.
    """
    return {
        "evidence_ids": _remap_list(
            original.get("evidence_ids", []), "evidence", idmap
        ),
        "transfer_ids": _remap_list(
            original.get("transfer_ids", []), "transfer", idmap
        ),
    }


def _primary_history(manifest, target, restore_id, history_id, data):
    """Build metadata for a restored primary history.

    Parameters
    ----------
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    restore_id : str
        Restore identifier.
    history_id : str
        New history identifier.
    data : bytes
        Restored transcript content.

    Returns
    -------
    dict
        Restored history metadata.
    """
    record = _history_identity(manifest, target, restore_id, history_id)
    record.update(_history_data(manifest, data))
    return record


def _history_identity(manifest, target, restore_id, history_id):
    """Build the identity fields of a restored history.

    Parameters
    ----------
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    restore_id : str
        Restore identifier.
    history_id : str
        New history identifier.

    Returns
    -------
    dict
        Identity fields.
    """
    record = {
        "id": history_id,
        "target_session_id": target["session_id"],
        "archive_id": manifest["archive_id"],
    }
    record.update(_history_identity_rest(manifest, restore_id))
    return record


def _history_data(manifest, data):
    """Build the timestamp and content fields of a restored history.

    Parameters
    ----------
    manifest : dict
        Verified archive manifest.
    data : bytes
        Restored transcript content.

    Returns
    -------
    dict
        Timestamp and content fields.
    """
    return {
        "archived_at": manifest.get("completed_at", 0),
        "restored_at": time.time(),
        "message_count": _line_count(data),
        "sha256": sha256_bytes(data),
        "read_only": True,
        "searchable": True,
    }


def _line_count(data):
    """Count non-empty JSONL transcript lines.

    Parameters
    ----------
    data : bytes
        Transcript content.

    Returns
    -------
    int
        Non-empty line count.
    """
    return len([line for line in data.splitlines() if line.strip()])


def _stage_threads(session, source, manifest, target, idmap):
    """Stage all archived research threads with new identifiers.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    source : pathlib.Path
        Archived session folder.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        Threads are staged.
    """
    folder = source / "research" / "threads"
    for path in sorted(folder.glob("*/meta.json")):
        _stage_thread(session, path, manifest, target, idmap)


def _stage_thread(session, path, manifest, target, idmap):
    """Stage one research thread.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    path : pathlib.Path
        Archived thread metadata path.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        The thread is staged.
    """
    meta = read_json(path)
    new_id_value = idmap.require("thread", meta["id"])
    record = _thread_record(meta, new_id_value, manifest, target, idmap)
    folder = session / "research" / "threads" / new_id_value
    _write_thread_files(folder, record, path.parent)


def _thread_record(meta, new_id_value, manifest, target, idmap):
    """Build restored thread metadata.

    Parameters
    ----------
    meta : dict
        Archived thread metadata.
    new_id_value : str
        New thread identifier.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Restored thread metadata.
    """
    record = copy.deepcopy(meta)
    record["id"] = new_id_value
    record["session_id"] = target["session_id"]
    record["restored"] = _restored_meta(manifest, meta["id"], idmap.restore_id)
    return record


def _stage_histories(session, source, manifest, target, idmap):
    """Stage archived restored histories with new identifiers.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    source : pathlib.Path
        Archived session folder.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        Restored histories are staged.
    """
    folder = source / "restored"
    for path in sorted(folder.glob("*/meta.json")):
        _stage_history(session, path, manifest, target, idmap)


def _stage_history(session, path, manifest, target, idmap):
    """Stage one archived restored history.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    path : pathlib.Path
        Archived history metadata path.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        The restored history is staged.
    """
    meta = read_json(path)
    new_id_value = idmap.require("restored_history", meta["id"])
    record = _archived_history(meta, new_id_value, manifest, target, idmap)
    folder = session / "restored" / new_id_value
    _write_thread_files(folder, record, path.parent)


def _archived_history(meta, new_id_value, manifest, target, idmap):
    """Build restored metadata for an archived restored history.

    Parameters
    ----------
    meta : dict
        Archived history metadata.
    new_id_value : str
        New history identifier.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Restored history metadata.
    """
    record = copy.deepcopy(meta)
    record["id"] = new_id_value
    record["target_session_id"] = target["session_id"]
    record["archive_id"] = manifest["archive_id"]
    record["restore_id"] = idmap.restore_id
    return record


def _stage_transfers(session, source, manifest, target, idmap):
    """Stage transfer history with remapped thread references.

    Parameters
    ----------
    session : pathlib.Path
        Staged session folder.
    source : pathlib.Path
        Archived session folder.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        Transfer records are staged.
    """
    records = _jsonl(source / "research" / "transfers.jsonl")
    if not records:
        return
    lines = [_transfer_line(item, manifest, target, idmap) for item in records]
    append_text(
        session / "research" / "transfers.jsonl", "\n".join(lines) + "\n"
    )


def _transfer_line(original, manifest, target, idmap):
    """Serialize one restored transfer record.

    Parameters
    ----------
    original : dict
        Archived transfer record.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    str
        JSON line.
    """
    record = _transfer_record(original, manifest, target, idmap)
    return json.dumps(record)


def _transfer_record(original, manifest, target, idmap):
    """Build one restored transfer record.

    Parameters
    ----------
    original : dict
        Archived transfer record.
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Restored transfer record.
    """
    record = copy.deepcopy(original)
    record["id"] = idmap.new("transfer", "tr", original.get("id"))
    record.update(_transfer_links(original, target, idmap))
    record["restored"] = _restored_meta(
        manifest, original.get("id"), idmap.restore_id
    )
    return record


def _stage_global(staging, source, target, idmap, manifest):
    """Stage global notes, sources, evidence, and tombstones.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    source : pathlib.Path
        Archived global folder.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    None
        Global records are staged.
    """
    _stage_notes(staging, source, target["session_id"], idmap, manifest)
    _stage_sources(staging, source, target["session_id"], idmap, manifest)
    _stage_evidence(staging, source, target["session_id"], idmap, manifest)
    _stage_tombstones(staging, source, target["session_id"], idmap, manifest)


def _stage_notes(staging, source, session_id, idmap, manifest):
    """Stage notes and every revision.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    source : pathlib.Path
        Archived global folder.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    None
        Notes and revisions are staged.
    """
    for path in sorted((source / "notes").glob("nt_*.json")):
        _stage_note(staging, path, session_id, idmap, manifest)
    for folder in sorted((source / "notes" / "revisions").glob("nt_*")):
        _stage_note_revisions(staging, folder, idmap)


def _stage_note(staging, path, session_id, idmap, manifest):
    """Stage one note record.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    path : pathlib.Path
        Archived note path.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    None
        The note is staged.
    """
    original = read_json(path)
    new_id_value = idmap.require("note", original["id"])
    record = _note_record(original, new_id_value, session_id, idmap, manifest)
    write_json_atomic(staging / "notes" / f"{new_id_value}.json", record)


def _note_record(original, new_id_value, session_id, idmap, manifest):
    """Build one restored note record.

    Parameters
    ----------
    original : dict
        Archived note record.
    new_id_value : str
        New note identifier.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    dict
        Restored note record.
    """
    record = copy.deepcopy(original)
    record["id"] = new_id_value
    record["scope"] = _scope_for(original.get("scope", {}), session_id, idmap)
    record.update(_note_refs(original, idmap))
    record["restored"] = _restored_meta(
        manifest, original["id"], idmap.restore_id
    )
    return record


def _stage_note_revisions(staging, folder, idmap):
    """Stage every revision of one note.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    folder : pathlib.Path
        Archived revision folder.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    None
        Revisions are staged.
    """
    new_id_value = idmap.require("note", folder.name)
    for path in sorted(folder.glob("r*.json")):
        _stage_revision(staging, path, new_id_value)


def _stage_revision(staging, path, note_id):
    """Stage one note revision.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    path : pathlib.Path
        Archived revision path.
    note_id : str
        New note identifier.

    Returns
    -------
    None
        The revision is staged.
    """
    record = read_json(path)
    record["note_id"] = note_id
    write_json_atomic(
        staging / "notes" / "revisions" / note_id / path.name, record
    )


def _stage_sources(staging, source, session_id, idmap, manifest):
    """Stage source records with remapped occurrences.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    source : pathlib.Path
        Archived global folder.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    None
        Sources are staged.
    """
    for path in sorted((source / "sources").glob("src_*.json")):
        _stage_source(staging, path, session_id, idmap, manifest)


def _stage_source(staging, path, session_id, idmap, manifest):
    """Stage one source record.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    path : pathlib.Path
        Archived source path.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    None
        The source is staged.
    """
    original = read_json(path)
    new_id_value = idmap.require("source", original["id"])
    record = _source_record(
        original, new_id_value, session_id, idmap, manifest
    )
    write_json_atomic(staging / "sources" / f"{new_id_value}.json", record)


def _source_record(original, new_id_value, session_id, idmap, manifest):
    """Build one restored source record.

    Parameters
    ----------
    original : dict
        Archived source record.
    new_id_value : str
        New source identifier.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    dict
        Restored source record.
    """
    record = copy.deepcopy(original)
    record["id"] = new_id_value
    record["scope"] = _scope_for(original.get("scope", {}), session_id, idmap)
    record["occurrences"] = _source_occurrences(original, idmap)
    record["restored"] = _restored_meta(
        manifest, original["id"], idmap.restore_id
    )
    return record


def _source_occurrence(original, idmap):
    """Build one restored source occurrence.

    Parameters
    ----------
    original : dict
        Archived occurrence.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Restored occurrence.
    """
    record = copy.deepcopy(original)
    record["thread_id"] = _remap(record.get("thread_id"), "thread", idmap)
    return record


def _stage_evidence(staging, source, session_id, idmap, manifest):
    """Stage evidence metadata and PNG files.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    source : pathlib.Path
        Archived global folder.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    None
        Evidence pairs are staged.
    """
    folder = source / "evidence"
    for path in sorted(folder.rglob("ev_*.json")):
        _stage_evidence_item(staging, path, session_id, idmap, manifest)


def _stage_evidence_item(staging, path, session_id, idmap, manifest):
    """Stage one evidence metadata and screenshot pair.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    path : pathlib.Path
        Archived metadata path.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    None
        The pair is staged.
    """
    original = read_json(path)
    new_id_value = idmap.require("evidence", original["id"])
    record = _evidence_record(
        original, new_id_value, session_id, idmap, manifest
    )
    folder = staging / "evidence" / session_id / record["scope"]["thread_id"]
    _write_evidence_files(folder, new_id_value, record, path)


def _evidence_record(original, new_id_value, session_id, idmap, manifest):
    """Build one restored evidence record.

    Parameters
    ----------
    original : dict
        Archived evidence record.
    new_id_value : str
        New evidence identifier.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    dict
        Restored evidence record.
    """
    record = copy.deepcopy(original)
    record["id"] = new_id_value
    record["scope"] = _scope_for(original.get("scope", {}), session_id, idmap)
    record["source_id"] = _remap(original.get("source_id"), "source", idmap)
    record["restored"] = _restored_meta(
        manifest, original["id"], idmap.restore_id
    )
    return record


def _stage_tombstones(staging, source, session_id, idmap, manifest):
    """Stage tombstones with remapped surviving references.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    source : pathlib.Path
        Archived global folder.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    None
        Tombstones are staged.
    """
    folder = source / "tombstones" / "threads"
    for path in sorted(folder.glob("*.json")):
        _stage_tombstone(staging, path, session_id, idmap, manifest)


def _stage_tombstone(staging, path, session_id, idmap, manifest):
    """Stage one thread tombstone.

    Parameters
    ----------
    staging : pathlib.Path
        Staged global folder.
    path : pathlib.Path
        Archived tombstone path.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    None
        The tombstone is staged.
    """
    original = read_json(path)
    new_id_value = idmap.require("tombstone", original["thread_id"])
    record = _tombstone_record(
        original, new_id_value, session_id, idmap, manifest
    )
    write_json_atomic(
        staging / "tombstones" / "threads" / f"{new_id_value}.json", record
    )


def _tombstone_record(original, new_id_value, session_id, idmap, manifest):
    """Build one restored tombstone record.

    Parameters
    ----------
    original : dict
        Archived tombstone.
    new_id_value : str
        New thread identifier.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.
    manifest : dict
        Verified archive manifest.

    Returns
    -------
    dict
        Restored tombstone.
    """
    record = copy.deepcopy(original)
    record["thread_id"] = new_id_value
    record["session_id"] = session_id
    record.update(_tombstone_links(original, idmap))
    record["restored"] = _restored_meta(
        manifest, original["thread_id"], idmap.restore_id
    )
    return record


def _commit_restore(root, target, staging):
    """Commit staged restore files into live storage.

    Parameters
    ----------
    root : pathlib.Path
        Global research root.
    target : dict
        Target session description.
    staging : pathlib.Path
        Restore staging folder.

    Returns
    -------
    None
        The restore is committed.
    """
    session = staging / "session"
    if target["existing"]:
        _merge_session(target["folder"], session)
    else:
        rename_atomic(session, target["folder"])
    _copy_staged_globals(root, staging / "global")


def _merge_session(destination, session):
    """Merge staged session records into an existing session.

    Parameters
    ----------
    destination : pathlib.Path
        Existing session folder.
    session : pathlib.Path
        Staged session folder.

    Returns
    -------
    None
        Staged records are merged.
    """
    for parts in _MERGE_PARTS:
        _merge_tree(session.joinpath(*parts), destination.joinpath(*parts))
    _append_transfer_file(
        session / "research" / "transfers.jsonl",
        destination / "research" / "transfers.jsonl",
    )


def _merge_tree(source, destination):
    """Copy a staged tree into an existing destination.

    Parameters
    ----------
    source : pathlib.Path
        Staged tree.
    destination : pathlib.Path
        Existing destination.

    Returns
    -------
    None
        The tree is copied when present.
    """
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def _append_transfer_file(source, destination):
    """Append staged transfer lines to the destination file.

    Parameters
    ----------
    source : pathlib.Path
        Staged transfer file.
    destination : pathlib.Path
        Existing transfer file.

    Returns
    -------
    None
        Lines are appended when present.
    """
    if source.exists():
        append_text(destination, source.read_text(encoding="utf-8"))


def _copy_staged_globals(root, staging):
    """Copy staged global records into the research stores.

    Parameters
    ----------
    root : pathlib.Path
        Global research root.
    staging : pathlib.Path
        Staged global folder.

    Returns
    -------
    None
        Files are written atomically.
    """
    if not staging.exists():
        return
    for path in staging.rglob("*"):
        if path.is_file():
            write_bytes_atomic(
                root / path.relative_to(staging), path.read_bytes()
            )


def _scope_for(scope, session_id, idmap):
    """Remap a record scope into a restored session.

    Parameters
    ----------
    scope : dict
        Archived scope.
    session_id : str
        Target session identifier.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Restored scope.
    """
    record = copy.deepcopy(scope)
    record["session_id"] = session_id
    record["thread_id"] = _remap(record.get("thread_id"), "thread", idmap)
    return record


def _remap(value, kind, idmap):
    """Remap one identifier when a mapping exists.

    Parameters
    ----------
    value : str or None
        Original identifier.
    kind : str
        Record kind.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    str or None
        Restored or original identifier.
    """
    if value is None:
        return None
    return idmap.get(kind, value) or value


def _remap_list(values, kind, idmap):
    """Remap a sequence of identifiers.

    Parameters
    ----------
    values : collections.abc.Iterable
        Original identifiers.
    kind : str
        Record kind.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    list
        Restored identifiers.
    """
    return [_remap(value, kind, idmap) for value in values]


def _restored_meta(manifest, original_id, restore_id):
    """Build the provenance metadata on a restored record.

    Parameters
    ----------
    manifest : dict
        Verified archive manifest.
    original_id : str or None
        Original record identifier.
    restore_id : str
        Restore identifier.

    Returns
    -------
    dict
        Provenance metadata.
    """
    return {
        "archive_id": manifest["archive_id"],
        "restore_id": restore_id,
        "original_id": original_id,
        "original_session_id": manifest["original_session_id"],
    }


def _jsonl(path):
    """Read a JSONL file into a list of mappings.

    Parameters
    ----------
    path : pathlib.Path
        JSONL path.

    Returns
    -------
    list
        Parsed records.
    """
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _read_bytes(path):
    """Read bytes from a path, or return empty bytes when absent.

    Parameters
    ----------
    path : pathlib.Path
        File path.

    Returns
    -------
    bytes
        File content or empty bytes.
    """
    return path.read_bytes() if path.exists() else b""


_MERGE_PARTS = (
    ("research", "threads"),
    ("restored",),
    ("research", "restores"),
)


def _ensure_dirs(*paths):
    """Create every given folder.

    Parameters
    ----------
    paths : tuple
        Folders to create.

    Returns
    -------
    None
        Every folder exists.
    """
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def _archive_journal(record, paths, archive_id):
    """Build archive journal fields.

    Parameters
    ----------
    record : SessionRecord
        Session to archive.
    paths : list
        Global record paths.
    archive_id : str
        Archive identifier.

    Returns
    -------
    dict
        Journal fields.
    """
    return {
        "operation": "archive",
        "archive_id": archive_id,
        "session_folder": str(record.folder),
        "global_paths": [str(path) for path in paths],
    }


def _restore_journal(manifest, target, idmap):
    """Build restore journal fields.

    Parameters
    ----------
    manifest : dict
        Verified archive manifest.
    target : dict
        Target session description.
    idmap : IdMap
        Planned identifier mapping.

    Returns
    -------
    dict
        Journal fields.
    """
    return {
        "operation": "restore",
        "restore_id": idmap.restore_id,
        "archive_id": manifest["archive_id"],
        "target_session_id": target["session_id"],
        "session_folder": str(target["folder"]),
        "existing": target["existing"],
    }


def _run_archive_steps(service, staging, record, paths, archive_id, journal):
    """Stage, verify, rename, and delete live archive data.

    Parameters
    ----------
    service : ArchiveService
        Owning service.
    staging : pathlib.Path
        Staging folder.
    record : SessionRecord
        Session to archive.
    paths : list
        Global record paths.
    archive_id : str
        Archive identifier.
    journal : Journal
        Operation journal.

    Returns
    -------
    None
        The archive is renamed and live data is removed.
    """
    _store_archive(
        staging, record, paths, archive_id, service.archives, service._fault
    )
    _after_archive_rename(service, record, paths, journal)


def _after_archive_rename(service, record, paths, journal):
    """Delete live data after an archive is safely renamed.

    Parameters
    ----------
    service : ArchiveService
        Owning service.
    record : SessionRecord
        Archived session.
    paths : list
        Global record paths.
    journal : Journal
        Operation journal.

    Returns
    -------
    None
        Live data is removed.
    """
    service._fault("archive_renamed")
    journal.write("renamed")
    service._fault("archive_before_delete")
    _delete_live(record, paths)
    service._fault("archive_after_delete")


def _complete_archive(journal, folder):
    """Remove an archive journal and return the manifest.

    Parameters
    ----------
    journal : Journal
        Operation journal.
    folder : pathlib.Path
        Completed archive folder.

    Returns
    -------
    dict
        Completed manifest.
    """
    journal.remove()
    return read_json(folder / _MANIFEST)


def _recover_one(service, path):
    """Dispatch one journal to its recovery handler.

    Parameters
    ----------
    service : ArchiveService
        Owning service.
    path : pathlib.Path
        Journal path.

    Returns
    -------
    None
        The journal is handled.
    """
    data = read_json(path)
    handler = _recovery_handler(service, data.get("operation"))
    if handler is not None:
        handler(data, path)


def _recovery_handler(service, operation):
    """Return the recovery handler for an operation.

    Parameters
    ----------
    service : ArchiveService
        Owning service.
    operation : str or None
        Journal operation name.

    Returns
    -------
    collections.abc.Callable or None
        Recovery handler.
    """
    handlers = {
        "archive": service._recover_archive,
        "restore": service._recover_restore,
        "purge": service._recover_purge,
    }
    return handlers.get(operation)


def _delete_journal_live(data):
    """Delete the live data recorded in an archive journal.

    Parameters
    ----------
    data : dict
        Archive journal data.

    Returns
    -------
    None
        Session and global records are removed.
    """
    for item in data.get("global_paths", []):
        Path(item).unlink(missing_ok=True)
    folder = data.get("session_folder")
    if folder:
        shutil.rmtree(folder, ignore_errors=True)


def _resume_commit(service, data, staging):
    """Resume an interrupted restore commit.

    Parameters
    ----------
    service : ArchiveService
        Owning service.
    data : dict
        Restore journal data.
    staging : pathlib.Path
        Restore staging folder.

    Returns
    -------
    None
        The commit is finished.
    """
    target = _journal_target(data)
    if target["existing"] or target["folder"].exists():
        _merge_session(target["folder"], staging / "session")
        _copy_staged_globals(service.root, staging / "global")
        return
    _commit_restore(service.root, target, staging)


def _journal_target(data):
    """Build a target session description from journal data.

    Parameters
    ----------
    data : dict
        Restore journal data.

    Returns
    -------
    dict
        Target session description.
    """
    return {
        "session_id": data["target_session_id"],
        "folder": Path(data["session_folder"]),
        "existing": bool(data.get("existing")),
        "archive_id": data["archive_id"],
    }


def _purge_remaining(purging, archive):
    """Finish a purge that was renamed but not deleted.

    Parameters
    ----------
    purging : pathlib.Path
        Purging folder.
    archive : pathlib.Path
        Archive folder.

    Returns
    -------
    None
        The archive is deleted.
    """
    if purging.exists():
        shutil.rmtree(purging)
        return
    if archive.exists():
        rename_atomic(archive, purging)
        shutil.rmtree(purging)
