"""Tests for agent note proposals and session-bound services."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gui.research.evidence import EvidenceStore
from gui.research.notes import NoteStore
from gui.research.proposals import ProposalStore
from gui.research.services import ResearchServices
from gui.research.sources import SourceStore

THREAD_ID = "th_" + "0" * 32


def _services(folder):
    """Build services bound to a temporary session and thread.

    Parameters
    ----------
    folder : str
        Temporary parent directory.

    Returns
    -------
    ResearchServices
        Bound services.
    """
    root = Path(folder)
    services = ResearchServices(
        NoteStore(root), SourceStore(root), EvidenceStore(root)
    )
    record = SimpleNamespace(folder=root / "session", session_id="session")
    thread = {"id": THREAD_ID, "title": "Topic"}
    services.bind(record, thread)
    return services


def _create_note(services):
    """Create one note for a proposal test.

    Parameters
    ----------
    services : ResearchServices
        Bound services.

    Returns
    -------
    dict
        Created note.
    """
    scope = services.scope
    return services.note_store.create(scope, "Old", "Body", {"role": "user"})


class ProposalTests(unittest.TestCase):
    """Verify proposal creation, approval, and revision behavior."""

    def test_create_proposal_is_pending(self) -> None:
        """Store a proposal without creating a note.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The proposal is pending and no note exists.
        """
        with tempfile.TemporaryDirectory() as folder:
            services = _services(folder)
            proposal = services.propose_note("Title", "Body")
            self.assertEqual(services.proposals()[0]["id"], proposal["id"])
            self.assertEqual(services.note_store.list("session"), [])

    def test_apply_proposal_creates_note_and_removes_proposal(self) -> None:
        """Persist an approved proposal as a note.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The note is stored and the proposal is gone.
        """
        with tempfile.TemporaryDirectory() as folder:
            services = _services(folder)
            proposal = services.propose_note("Title", "Body")
            note = services.apply_proposal(proposal["id"])
            self.assertEqual(note["title"], "Title")
            self.assertEqual(services.proposals(), [])

    def test_revision_proposal_updates_existing_note(self) -> None:
        """Apply a revision proposal through the note store.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The note revision increments.
        """
        with tempfile.TemporaryDirectory() as folder:
            services = _services(folder)
            note = _create_note(services)
            proposal = services.propose_revision(note["id"], "New", "New body")
            updated = services.apply_proposal(proposal["id"])
            self.assertEqual(updated["revision"], 2)
            self.assertEqual(updated["title"], "New")

    def test_unbound_service_raises(self) -> None:
        """Reject proposals before a thread is bound.

        Parameters
        ----------
        None

        Returns
        -------
        None
            RuntimeError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            services = ResearchServices(
                NoteStore(root), SourceStore(root), EvidenceStore(root)
            )
            with self.assertRaises(RuntimeError):
                services.propose_note("T", "B")

    def test_proposal_store_round_trip(self) -> None:
        """List and remove a pending proposal.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The proposal can be loaded and removed.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = ProposalStore(Path(folder) / "session")
            scope = {"session_id": "session"}
            proposal = store.create(scope, {"role": "user"}, "T", "B")
            self.assertEqual(store.get(proposal["id"])["title"], "T")
            store.remove(proposal["id"])
            self.assertEqual(store.list(), [])


if __name__ == "__main__":
    unittest.main()
