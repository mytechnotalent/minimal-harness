"""Tests for archive purge, journals, recovery, and fault injection."""

import tempfile
import unittest

from gui.research.archive import ArchiveService
from gui.research.evidence import EvidenceStore
from gui.research.notes import NoteStore
from gui.research.sources import SourceStore

from .test_research_archive import _fixture


class _Fault:
    """Raise when a named fault injection point is reached."""

    def __init__(self, target):
        """Store the point that should raise.

        Parameters
        ----------
        target : str
            Fault point name.

        Returns
        -------
        None
            The hook is ready.
        """
        self.target = target

    def __call__(self, point):
        """Raise when the point matches.

        Parameters
        ----------
        point : str
            Fault point name.

        Returns
        -------
        None
            The hook returns for other points.
        """
        if point == self.target:
            raise RuntimeError(point)


def _service(fixture, fault=None):
    """Build an archive service for a fixture.

    Parameters
    ----------
    fixture : dict
        Fixture records and stores.
    fault : collections.abc.Callable or None
        Optional fault hook.

    Returns
    -------
    ArchiveService
        Service under test.
    """
    return ArchiveService(fixture["root"], fixture["store"].root, fault)


def _archive(service, fixture):
    """Archive the fixture session through a service.

    Parameters
    ----------
    service : ArchiveService
        Archive service.
    fixture : dict
        Fixture records and stores.

    Returns
    -------
    dict
        Completed manifest.
    """
    return service.archive_session(
        fixture["record"],
        fixture["notes"],
        fixture["sources"],
        fixture["evidence"],
    )


def _journals(root):
    """Return the journal files under a research root.

    Parameters
    ----------
    root : pathlib.Path
        Research root.

    Returns
    -------
    list
        Journal paths.
    """
    return list((root / "journals").glob("*.json"))


def _restore_stores(root):
    """Build the stores used by a restore.

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


def _run_faulty_archive(case, service, fixture):
    """Run an archive expected to hit a fault.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    service : ArchiveService
        Service with a fault hook.
    fixture : dict
        Fixture records and stores.

    Returns
    -------
    None
        The fault is raised.
    """
    with case.assertRaises(RuntimeError):
        _archive(service, fixture)


def _run_faulty_purge(case, service, archive_id):
    """Run a purge expected to hit a fault.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    service : ArchiveService
        Service with a fault hook.
    archive_id : str
        Archive identifier.

    Returns
    -------
    None
        The fault is raised.
    """
    with case.assertRaises(RuntimeError):
        service.purge(archive_id)


def _run_faulty_restore(case, service, archive_id, session_id, stores):
    """Run a restore expected to hit a fault.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    service : ArchiveService
        Service with a fault hook.
    archive_id : str
        Archive identifier.
    session_id : str
        Target session identifier.
    stores : tuple
        Note, source, and evidence stores.

    Returns
    -------
    None
        The fault is raised.
    """
    with case.assertRaises(RuntimeError):
        service.restore(archive_id, session_id, None, *stores)


def _assert_purge_isolation(case, fixture, service, manifest, result):
    """Assert a purge removed only the archive.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    fixture : dict
        Fixture records and stores.
    service : ArchiveService
        Service used by the purge.
    manifest : dict
        Archive manifest.
    result : dict
        Restore result.

    Returns
    -------
    None
        Purge assertions pass.
    """
    archive = fixture["root"] / "archives" / manifest["archive_id"]
    restored = fixture["store"].root / result["target_session_id"]
    case.assertFalse(archive.exists())
    case.assertTrue(restored.exists())
    case.assertEqual(service.list(), [])
    case.assertEqual(_journals(fixture["root"]), [])


def _assert_archive_finished(case, fixture, service):
    """Assert that recovery finished an interrupted archive.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    fixture : dict
        Fixture records and stores.
    service : ArchiveService
        Service used by recovery.

    Returns
    -------
    None
        Archive recovery assertions pass.
    """
    case.assertTrue(fixture["record"].folder.exists())
    case.assertEqual(len(_journals(fixture["root"])), 1)
    service.recover()
    case.assertFalse(fixture["record"].folder.exists())
    case.assertEqual(_journals(fixture["root"]), [])
    case.assertEqual(len(service.list()), 1)


def _assert_archive_rolled_back(case, fixture, service):
    """Assert that recovery rolled back an incomplete archive.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    fixture : dict
        Fixture records and stores.
    service : ArchiveService
        Service used by recovery.

    Returns
    -------
    None
        Rollback assertions pass.
    """
    case.assertTrue(fixture["record"].folder.exists())
    service.recover()
    case.assertEqual(service.list(), [])
    case.assertTrue(fixture["record"].folder.exists())


def _assert_purge_finished(case, fixture, manifest, service):
    """Assert that recovery finished a renamed purge.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    fixture : dict
        Fixture records and stores.
    manifest : dict
        Archive manifest.
    service : ArchiveService
        Service used by recovery.

    Returns
    -------
    None
        Purge recovery assertions pass.
    """
    purging = fixture["root"] / ".purging" / manifest["archive_id"]
    case.assertTrue(purging.exists())
    service.recover()
    case.assertFalse(purging.exists())
    case.assertEqual(_journals(fixture["root"]), [])


def _assert_restore_rolled_back(case, fixture, service, session_id):
    """Assert that recovery rolled back an uncommitted restore.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    fixture : dict
        Fixture records and stores.
    service : ArchiveService
        Service used by recovery.
    session_id : str
        Target session identifier.

    Returns
    -------
    None
        Rollback assertions pass.
    """
    target = fixture["store"].root / session_id
    case.assertFalse(target.exists())
    service.recover()
    case.assertEqual(_journals(fixture["root"]), [])
    case.assertFalse(target.exists())


def _assert_restore_kept(case, fixture, service, manifest, stores):
    """Assert that recovery kept a committed restore.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    fixture : dict
        Fixture records and stores.
    service : ArchiveService
        Service used by recovery.
    manifest : dict
        Archive manifest.
    stores : tuple
        Note, source, and evidence stores.

    Returns
    -------
    None
        Committed restore assertions pass.
    """
    case.assertEqual(len(_journals(fixture["root"])), 1)
    service.recover()
    case.assertEqual(_journals(fixture["root"]), [])
    case.assertEqual(len(stores[0].list("done1", status=None)), 1)
    case.assertTrue(service.verify(manifest["archive_id"])["ok"])


def _archived_restore(folder):
    """Build a fixture, archive it, and restore it into a new session.

    Parameters
    ----------
    folder : str
        Temporary parent directory.

    Returns
    -------
    tuple
        Fixture, service, manifest, and restore result.
    """
    fixture = _fixture(folder)
    service = _service(fixture)
    manifest = _archive(service, fixture)
    stores = _restore_stores(fixture["root"])
    result = service.restore(manifest["archive_id"], None, None, *stores)
    return fixture, service, manifest, result


def _crashed_restore(case, folder, point, session_id):
    """Run a restore that raises at one fault point.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    folder : str
        Temporary parent directory.
    point : str
        Fault point name.
    session_id : str
        Target session identifier.

    Returns
    -------
    tuple
        Fixture, service, manifest, crashing service, and stores.
    """
    fixture, service, manifest, crashing = _crash_state(folder, point)
    stores = _restore_stores(fixture["root"])
    _run_faulty_restore(
        case, crashing, manifest["archive_id"], session_id, stores
    )
    return fixture, service, manifest, crashing, stores


def _crash_state(folder, point):
    """Build a fixture, archive, and a faulting restore service.

    Parameters
    ----------
    folder : str
        Temporary parent directory.
    point : str
        Fault point name.

    Returns
    -------
    tuple
        Fixture, service, manifest, and crashing service.
    """
    fixture = _fixture(folder)
    service = _service(fixture)
    manifest = _archive(service, fixture)
    crashing = _service(fixture, _Fault(point))
    return fixture, service, manifest, crashing


class PurgeTests(unittest.TestCase):
    """Verify rename-first purge and restored copy isolation."""

    def test_purge_removes_archive_only(self) -> None:
        """Delete the archive and leave restored copies alone.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The archive is gone and the restored session survives.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture, service, manifest, result = _archived_restore(folder)
            service.purge(manifest["archive_id"])
            _assert_purge_isolation(self, fixture, service, manifest, result)

    def test_purge_unknown_archive_raises(self) -> None:
        """Reject a purge for a missing archive.

        Parameters
        ----------
        None

        Returns
        -------
        None
            FileNotFoundError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            service = _service(fixture)
            with self.assertRaises(FileNotFoundError):
                service.purge("ar_" + "0" * 32)


class RecoveryTests(unittest.TestCase):
    """Verify journals resume or roll back interrupted operations."""

    def test_archive_crash_before_delete_is_finished(self) -> None:
        """Finish live deletion after a crash following the rename.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The archive survives and live data disappears.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            service = _service(fixture, _Fault("archive_before_delete"))
            _run_faulty_archive(self, service, fixture)
            _assert_archive_finished(self, fixture, service)

    def test_archive_crash_during_staging_rolls_back(self) -> None:
        """Roll back staging when the archive never completes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Live data survives and no archive remains.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            service = _service(fixture, _Fault("archive_staged"))
            _run_faulty_archive(self, service, fixture)
            _assert_archive_rolled_back(self, fixture, service)

    def test_purge_crash_after_rename_is_finished(self) -> None:
        """Finish deleting a purge that was renamed first.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The purging folder and journal are removed.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture = _fixture(folder)
            service = _service(fixture)
            manifest = _archive(service, fixture)
            crashing = _service(fixture, _Fault("purge_renamed"))
            _run_faulty_purge(self, crashing, manifest["archive_id"])
            _assert_purge_finished(self, fixture, manifest, crashing)

    def test_restore_crash_before_commit_rolls_back(self) -> None:
        """Remove staged restore files when commit never begins.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No target session and no journal remain.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture, _, _, crashing, _ = _crashed_restore(
                self, folder, "restore_staged", "staged1"
            )
            _assert_restore_rolled_back(self, fixture, crashing, "staged1")

    def test_restore_crash_after_commit_keeps_records(self) -> None:
        """Keep a committed restore and clean up its journal.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Records are not duplicated by recovery.
        """
        with tempfile.TemporaryDirectory() as folder:
            fixture, service, manifest, _, stores = _crashed_restore(
                self, folder, "restore_committed", "done1"
            )
            _assert_restore_kept(self, fixture, service, manifest, stores)


if __name__ == "__main__":
    unittest.main()
