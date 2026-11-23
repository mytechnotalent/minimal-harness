"""Session-bound services for agent note proposals and evidence."""

import time
from pathlib import Path
from tempfile import NamedTemporaryFile

from meta_harness.browser import BrowserClient

from .proposals import ProposalStore


class ResearchServices:
    """Bind note, source, and evidence operations to one research thread."""

    def __init__(self, note_store, source_store, evidence_store):
        """Store the global research stores.

        Parameters
        ----------
        note_store : NoteStore
            Global note store.
        source_store : SourceStore
            Global source store.
        evidence_store : EvidenceStore
            Global evidence store.

        Returns
        -------
        None
            The service starts unbound.
        """
        self.note_store = note_store
        self.source_store = source_store
        self.evidence_store = evidence_store
        self.session_folder = None
        self.scope = None

    def use_stores(self, note_store, source_store, evidence_store):
        """Replace the global stores after a workspace change.

        Parameters
        ----------
        note_store : NoteStore or None
            Global note store.
        source_store : SourceStore or None
            Global source store.
        evidence_store : EvidenceStore or None
            Global evidence store.

        Returns
        -------
        None
            Store references are updated.
        """
        self.note_store = note_store
        self.source_store = source_store
        self.evidence_store = evidence_store

    def bind(self, record, thread):
        """Bind the service to a session and thread.

        Parameters
        ----------
        record : SessionRecord
            Active primary session.
        thread : dict
            Active research thread.

        Returns
        -------
        None
            Scope and proposal storage are ready.
        """
        self.session_folder = record.folder
        self.scope = {
            "session_id": record.session_id,
            "thread_id": thread["id"],
            "thread_title_snapshot": thread.get("title", ""),
            "thread_deleted": False,
        }

    def propose_note(self, title, body_md):
        """Create a pending note proposal.

        Parameters
        ----------
        title : str
            Proposed title.
        body_md : str
            Proposed markdown body.

        Returns
        -------
        dict
            Pending proposal.
        """
        self._require_bound()
        return self._proposals().create(
            self.scope, _origin(body_md), title, body_md
        )

    def propose_revision(self, note_id, title, body_md):
        """Create a pending revision proposal for a note.

        Parameters
        ----------
        note_id : str
            Existing note identifier.
        title : str
            Proposed title.
        body_md : str
            Proposed markdown body.

        Returns
        -------
        dict
            Pending proposal.
        """
        self._require_bound()
        note = self.note_store.get(note_id)
        _require_same_session(note, self.scope["session_id"])
        return self._proposals().create(
            self.scope, _origin(body_md), title, body_md, note_id
        )

    def proposals(self):
        """Return pending note proposals.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Pending proposal records.
        """
        if self.session_folder is None:
            return []
        return self._proposals().list()

    def apply_proposal(self, proposal_id):
        """Persist an approved proposal as a note or revision.

        Parameters
        ----------
        proposal_id : str
            Proposal identifier.

        Returns
        -------
        dict
            Saved note record.
        """
        self._require_bound()
        store = self._proposals()
        proposal = store.get(proposal_id)
        note = self._apply(proposal)
        store.remove(proposal_id)
        return note

    def discard_proposal(self, proposal_id):
        """Delete a pending proposal.

        Parameters
        ----------
        proposal_id : str
            Proposal identifier.

        Returns
        -------
        None
            The proposal is removed.
        """
        self._require_bound()
        self._proposals().remove(proposal_id)

    def capture_evidence(self, url, caption=""):
        """Capture a safe browser screenshot into the evidence store.

        Parameters
        ----------
        url : str
            Page URL.
        caption : str
            Optional caption.

        Returns
        -------
        dict
            Evidence record.
        """
        self._require_bound()
        data = _screenshot(url)
        source_id = self._source_id(url)
        return self.evidence_store.capture(
            self.scope, url, data, source_id=source_id, caption=caption
        )

    def _apply(self, proposal):
        """Persist one proposal through the note store.

        Parameters
        ----------
        proposal : dict
            Pending proposal.

        Returns
        -------
        dict
            Saved note record.
        """
        if proposal["kind"] == "revision":
            return self._apply_revision(proposal)
        return self._apply_create(proposal)

    def _apply_revision(self, proposal):
        """Persist a revision proposal.

        Parameters
        ----------
        proposal : dict
            Revision proposal.

        Returns
        -------
        dict
            Updated note.
        """
        return self.note_store.update(
            proposal["note_id"],
            title=proposal["title"],
            body_md=proposal["body_md"],
        )

    def _apply_create(self, proposal):
        """Persist a new-note proposal.

        Parameters
        ----------
        proposal : dict
            Create proposal.

        Returns
        -------
        dict
            New note.
        """
        return self.note_store.create(
            proposal["scope"],
            proposal["title"],
            proposal["body_md"],
            proposal["origin"],
        )

    def _proposals(self):
        """Return the proposal store for the bound session.

        Parameters
        ----------
        None

        Returns
        -------
        ProposalStore
            Session proposal store.
        """
        return ProposalStore(self.session_folder)

    def _source_id(self, url):
        """Return a matching captured source identifier.

        Parameters
        ----------
        url : str
            Page URL.

        Returns
        -------
        str or None
            Source identifier when found.
        """
        for source in self.source_store.list(
            self.scope["session_id"], status=None
        ):
            if source.get("url") == url:
                return source["id"]
        return None

    def _require_bound(self):
        """Reject service calls before binding.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The service is bound.
        """
        if self.scope is None:
            raise RuntimeError("research services are not bound")


def _origin(body_md):
    """Build a proposal origin snapshot.

    Parameters
    ----------
    body_md : str
        Proposed markdown body.

    Returns
    -------
    dict
        Origin snapshot.
    """
    return {
        "message_seq": None,
        "message_hash": "",
        "role": "agent",
        "excerpt": body_md[:500],
        "captured_at": time.time(),
    }


def _require_same_session(note, session_id):
    """Reject a revision proposal for another session.

    Parameters
    ----------
    note : dict
        Note record.
    session_id : str
        Bound session identifier.

    Returns
    -------
    None
        The note belongs to the session.
    """
    if note.get("scope", {}).get("session_id") != session_id:
        raise RuntimeError("note is outside the active session")


def _screenshot(url):
    """Capture a page screenshot into memory.

    Parameters
    ----------
    url : str
        Page URL.

    Returns
    -------
    bytes
        PNG content.
    """
    with NamedTemporaryFile(suffix=".png", delete=False) as handle:
        path = Path(handle.name)
    try:
        BrowserClient(safe=True).screenshot(url, str(path))
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)
