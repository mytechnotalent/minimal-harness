"""Complete archive snapshots of research sessions and their records."""

import shutil
import time
from pathlib import Path

from .atomic import read_json
from .atomic import rename_atomic
from .atomic import write_bytes_atomic
from .atomic import write_json_atomic
from .hashing import sha256_file
from .ids import new_id
from .ids import require_id
from .schemas import validate_record

ARCHIVE_PREFIX = "ar"
FORMAT_VERSION = 1
_MANIFEST = "manifest.json"
_DIGEST = "manifest.sha256"
_STEM_KINDS = frozenset(
    {"note", "source", "evidence_meta", "evidence_png", "tombstone"}
)


class ArchiveError(RuntimeError):
    """Report an archive operation that cannot complete."""


class ArchiveService:
    """Archive and verify complete research session snapshots."""

    def __init__(self, research_root):
        """Prepare archive storage under a research root.

        Parameters
        ----------
        research_root : pathlib.Path or str
            Global research data root.

        Returns
        -------
        None
            The archive directory exists.
        """
        self.root = Path(research_root)
        self.archives = self.root / "archives"
        self.staging = self.archives / ".staging"
        self.archives.mkdir(parents=True, exist_ok=True)

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
        try:
            _store_archive(staging, record, paths, archive_id, self.archives)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return _purge_live(record, paths, self.archives / archive_id)

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


def _store_archive(staging, record, paths, archive_id, archives):
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

    Returns
    -------
    None
        The archive is verified and renamed.
    """
    manifest = _stage_archive(staging, record, paths, archive_id)
    _require_verified(_verify(staging, manifest))
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
